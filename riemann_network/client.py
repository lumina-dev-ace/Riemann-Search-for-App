"""Credential-free, read-only access to public RiemannSearch network data.

This module deliberately does not publish data. Until a reviewed and secure
publishing service exists, contributors should submit pull requests.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


DEFAULT_REPOSITORY = "lumina-dev-ace/Riemann-Search-for-App"
DEFAULT_REF = "main"
T = TypeVar("T")


class NetworkError(Exception):
    """Base class for network-client errors."""


class NetworkUnavailableError(NetworkError):
    """The network is unavailable and no usable cached response exists."""


@dataclass(frozen=True)
class NetworkResponse(Generic[T]):
    data: T
    source: Literal["network", "cache"]
    fetched_utc: str
    stale: bool = False


@dataclass(frozen=True)
class CheckpointSnapshot:
    status: Literal["uninitialized", "initialized"]
    highest_verified_index: int | None
    updated_utc: str | None
    source_commit: str | None
    record_count: int


def _parse_checkpoint(payload: Any) -> CheckpointSnapshot:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NetworkError("Unsupported or malformed checkpoint document")
    status = payload.get("status")
    high = payload.get("highest_verified_index")
    if status == "uninitialized":
        if high is not None:
            raise NetworkError("Uninitialized checkpoint unexpectedly contains an index")
    elif status == "initialized":
        if isinstance(high, bool) or not isinstance(high, int) or high < 1:
            raise NetworkError("Initialized checkpoint has an invalid highest index")
    else:
        raise NetworkError("Checkpoint status is not recognized")
    count = payload.get("record_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise NetworkError("Checkpoint record_count is invalid")
    updated = payload.get("updated_utc")
    source_commit = payload.get("source_commit")
    if status == "initialized":
        if not isinstance(updated, str) or not isinstance(source_commit, str):
            raise NetworkError("Initialized checkpoint is missing provenance")
    return CheckpointSnapshot(
        status=status,
        highest_verified_index=high,
        updated_utc=updated,
        source_commit=source_commit,
        record_count=count,
    )


def _validate_record_payload(payload: Any, expected_name: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise NetworkError("Unsupported or malformed research record")
    record_id = payload.get("record_id")
    if not isinstance(record_id, str) or record_id + ".json" != expected_name:
        raise NetworkError("Record identity does not match its filename")
    start, end = payload.get("start_index"), payload.get("end_index")
    entries = payload.get("entries")
    if (isinstance(start, bool) or not isinstance(start, int) or start < 1
            or isinstance(end, bool) or not isinstance(end, int) or end < start
            or not isinstance(entries, list) or len(entries) != end - start + 1):
        raise NetworkError("Research record range is malformed")
    for offset, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get("index") != start + offset:
            raise NetworkError("Research record entries are not contiguous")
        if entry.get("status") not in ("candidate", "evaluated", "arb_verified"):
            raise NetworkError("Research record contains an unknown entry status")
    return payload


class NetworkClient:
    """Fetch the published checkpoint and records without any GitHub secret.

    Responses are cached in memory and, optionally, in cache_dir. If a refresh
    fails, the client can return an older cached response with stale=True;
    callers must label stale data in the user interface.
    """

    def __init__(
        self,
        repository: str = DEFAULT_REPOSITORY,
        ref: str = DEFAULT_REF,
        timeout_seconds: float = 8.0,
        cache_dir: str | Path | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("repository must be in owner/name format")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref) or ".." in ref.split("/"):
            raise ValueError("ref contains unsupported characters")
        if timeout_seconds <= 0 or cache_ttl_seconds < 0:
            raise ValueError("timeout must be positive and cache TTL non-negative")
        self.repository = repository
        self.ref = ref
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._memory_cache: dict[str, tuple[Any, datetime]] = {}

    def _raw_url(self, path: str) -> str:
        return f"https://raw.githubusercontent.com/{self.repository}/{quote(self.ref, safe='')}/{quote(path, safe='/')}"

    def _cache_file(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / (digest + ".json")

    def _read_cache(self, url: str) -> tuple[Any, datetime] | None:
        cached = self._memory_cache.get(url)
        if cached is not None:
            return cached
        path = self._cache_file(url)
        if path is None or not path.exists():
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(envelope["fetched_utc"].replace("Z", "+00:00"))
            item = (envelope["data"], fetched)
            self._memory_cache[url] = item
            return item
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return None

    def _write_cache(self, url: str, data: Any, fetched: datetime) -> None:
        self._memory_cache[url] = (data, fetched)
        path = self._cache_file(url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "fetched_utc": fetched.isoformat().replace("+00:00", "Z"),
            "data": data,
        }
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False
            ) as handle:
                temporary_name = handle.name
                json.dump(envelope, handle)
                handle.write("\n")
            Path(temporary_name).replace(path)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink(missing_ok=True)

    def _get_json(self, url: str, *, force_refresh: bool = False) -> NetworkResponse[Any]:
        cached = self._read_cache(url)
        now = datetime.now(timezone.utc)
        if cached and not force_refresh:
            data, fetched = cached
            age = (now - fetched).total_seconds()
            if age <= self.cache_ttl_seconds:
                return NetworkResponse(data, "cache", fetched.isoformat(), False)

        headers = {"User-Agent": "RiemannSearch-Research-Network/1.0", "Accept": "application/json"}
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            if cached:
                data, fetched = cached
                return NetworkResponse(data, "cache", fetched.isoformat(), True)
            raise NetworkUnavailableError(f"Research network could not be reached: {exc}") from exc

        self._write_cache(url, payload, now)
        return NetworkResponse(payload, "network", now.isoformat(), False)

    def get_checkpoint(self, *, force_refresh: bool = False) -> NetworkResponse[CheckpointSnapshot]:
        url = self._raw_url("global/checkpoint.json")
        response = self._get_json(url, force_refresh=force_refresh)
        return NetworkResponse(
            _parse_checkpoint(response.data),
            response.source,
            response.fetched_utc,
            response.stale,
        )

    def list_records(self, *, force_refresh: bool = False) -> NetworkResponse[list[str]]:
        url = f"https://api.github.com/repos/{self.repository}/contents/records?ref={quote(self.ref, safe='')}"
        response = self._get_json(url, force_refresh=force_refresh)
        if not isinstance(response.data, list):
            raise NetworkError("GitHub records listing is not an array")
        names = sorted(
            item["name"]
            for item in response.data
            if isinstance(item, dict)
            and item.get("type") == "file"
            and isinstance(item.get("name"), str)
            and re.fullmatch(r"[A-Za-z0-9._-]+\.json", item["name"])
        )
        return NetworkResponse(names, response.source, response.fetched_utc, response.stale)

    def fetch_record(self, filename: str, *, force_refresh: bool = False) -> NetworkResponse[dict[str, Any]]:
        if not re.fullmatch(r"[A-Za-z0-9._-]+\.json", filename):
            raise ValueError("filename must be a simple JSON record filename")
        url = self._raw_url("records/" + filename)
        response = self._get_json(url, force_refresh=force_refresh)
        payload = _validate_record_payload(response.data, filename)
        return NetworkResponse(payload, response.source, response.fetched_utc, response.stale)
