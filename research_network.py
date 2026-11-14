"""Validated, public GitHub research-manifest access and safe publication.

GitHub is the single source of truth for shared progress. The desktop keeps a
validated cache for display, but a cache is never treated as a current import.
Numerical results remain local and are only exported/published after strict
consecutiveness and verification-metadata checks.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


REPOSITORY = "lumina-dev-ace/Riemann-Search-for-App"
REPOSITORY_URL = f"https://github.com/{REPOSITORY}"
MANIFEST_PATH = "data/global_manifest.json"
SCHEMA_VERSION = 1
BACKEND_INDEX_LIMIT = 10**37
GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
_NONNEGATIVE_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z")
_MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
_ALLOWED_VERIFICATION = {"verified", "certified_interval_rechecked"}
_GIT_REF_INVALID = re.compile(r"[\x00-\x20\x7f~^:?*\\\[]")


def _validate_branch_name(branch: Optional[str]) -> Optional[str]:
    """Validate an optional repository branch override without shell/path semantics."""
    if branch is None or branch == "":
        return None
    if not isinstance(branch, str) or len(branch) > 255:
        raise ValueError("GitHub branch must be a valid short ref name")
    if (
        branch.startswith("/") or branch.endswith(("/", ".")) or "//" in branch
        or ".." in branch or "@{" in branch or branch == "@"
        or _GIT_REF_INVALID.search(branch)
        or any(part.startswith(".") or part.endswith(".lock") for part in branch.split("/"))
    ):
        raise ValueError("GitHub branch must be a valid short ref name")
    return branch


class ResearchNetworkError(RuntimeError):
    """Base class for repository, validation, and publication failures."""


class ManifestMissingError(ResearchNetworkError):
    """The specified repository has not published its manifest yet."""


class ManifestValidationError(ResearchNetworkError):
    """The remote or local manifest/record failed strict validation."""


class StaleGlobalCheckpointError(ResearchNetworkError):
    """The imported manifest is no longer the current publication base."""


class SubmissionRejectedError(ResearchNetworkError):
    """A range does not extend the current consecutively accepted coverage."""


def _unique_object(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ManifestValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json_bytes(data: bytes) -> Any:
    try:
        return json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ManifestValidationError(f"Invalid JSON numeric constant: {value}")
            ),
        )
    except UnicodeDecodeError as exc:
        raise ManifestValidationError("JSON must be UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ManifestValidationError(f"Invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(document: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestValidationError("Document cannot be encoded as canonical JSON") from exc


def document_sha256(document: Mapping[str, Any], *, integrity_key: str = "integrity") -> str:
    payload = dict(document)
    payload.pop(integrity_key, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def seal_document(document: Mapping[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(dict(document))
    result.pop("integrity", None)
    result["integrity"] = {"algorithm": "sha256", "sha256": document_sha256(result)}
    return result


def serialize_document(document: Mapping[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def exact_index(value: Any, label: str, *, allow_zero: bool = False) -> int:
    if not isinstance(value, str) or not _DECIMAL.fullmatch(value):
        raise ManifestValidationError(f"{label} must be a canonical decimal string")
    number = int(value)
    if (number == 0 and not allow_zero) or number < 0:
        raise ManifestValidationError(f"{label} must be a positive index")
    if number >= BACKEND_INDEX_LIMIT:
        raise ManifestValidationError(
            f"{label} {value} is outside the current FLINT indexed-zero range (n < 10^37)"
        )
    return number


def _require_nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestValidationError(f"{label} must be a non-empty string")
    return value


def _verify_document_integrity(document: Mapping[str, Any], label: str) -> None:
    integrity = document.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("algorithm") != "sha256":
        raise ManifestValidationError(f"{label} is missing its SHA-256 integrity record")
    expected = integrity.get("sha256")
    if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
        raise ManifestValidationError(f"{label} has an invalid integrity hash")
    actual = document_sha256(document)
    if not hmac.compare_digest(expected, actual):
        raise ManifestValidationError(f"{label} SHA-256 integrity check failed")


def validate_research_record(record: Mapping[str, Any]) -> Tuple[int, int]:
    """Validate a versioned range record and derive its endpoint from results."""
    if not isinstance(record, Mapping) or record.get("schema_version") != SCHEMA_VERSION:
        raise ManifestValidationError("Research record has an unsupported schema version")
    if record.get("record_type") != "riemannsearch-zero-range":
        raise ManifestValidationError("Research record has an unsupported record type")
    _verify_document_integrity(record, "Research record")

    computation = record.get("computation")
    verification = record.get("verification")
    results = record.get("results")
    if not isinstance(computation, dict) or not isinstance(verification, dict):
        raise ManifestValidationError("Research record is missing computation or verification metadata")
    backend = _require_nonempty_text(computation.get("backend"), "Computation backend").casefold()
    if "flint" not in backend and "arb" not in backend:
        raise ManifestValidationError("Only FLINT/Arb-backed numerical records are eligible for global publication")
    _require_nonempty_text(computation.get("backend_version"), "Backend version")
    _require_nonempty_text(computation.get("algorithm"), "Numerical algorithm")
    _require_nonempty_text(verification.get("method"), "Verification method")
    if "arb" not in verification["method"].casefold():
        raise ManifestValidationError("Global publication requires recorded Arb verification")
    for key, label in (("precision_digits", "Computation precision"),):
        if type(computation.get(key)) is not int or computation[key] < 2:
            raise ManifestValidationError(f"{label} must be an integer of at least 2 digits")
    if type(verification.get("precision_digits")) is not int or verification["precision_digits"] < 2:
        raise ManifestValidationError("Verification precision must be an integer of at least 2 digits")
    if not isinstance(results, list) or not results:
        raise ManifestValidationError("Research record must contain at least one computed result")

    first: Optional[int] = None
    previous: Optional[int] = None
    statuses = set()
    intervals = []
    for row_number, result in enumerate(results, start=1):
        if not isinstance(result, dict):
            raise ManifestValidationError(f"Result {row_number} must be an object")
        index = exact_index(result.get("zero_index"), f"Result {row_number} zero_index")
        if first is None:
            first = index
        if previous is not None and index != previous + 1:
            raise ManifestValidationError(
                f"Results are not consecutive: expected {previous + 1}, found {index}"
            )
        previous = index
        for field in ("real_part", "imag_part", "residual", "verification_residual", "computed_at"):
            _require_nonempty_text(result.get(field), f"Result {index} {field}")
        status = result.get("verification_status")
        if status not in _ALLOWED_VERIFICATION:
            raise ManifestValidationError(
                f"Result {index} is not an eligible Arb-rechecked result (status={status!r})"
            )
        statuses.add(status)
        intervals.append(bool(result.get("certified_interval")))
        if type(result.get("precision_digits")) is not int or result["precision_digits"] < 2:
            raise ManifestValidationError(f"Result {index} has invalid computation precision")
        if type(result.get("verification_precision_digits")) is not int or result["verification_precision_digits"] < 2:
            raise ManifestValidationError(f"Result {index} has invalid verification precision")
        for field in ("computation_time_ms", "verification_time_ms"):
            timing = result.get(field)
            if timing is not None:
                if not isinstance(timing, str) or not _NONNEGATIVE_DECIMAL.fullmatch(timing):
                    raise ManifestValidationError(f"Result {index} {field} must be a non-negative decimal string or null")
                try:
                    if not Decimal(timing).is_finite():
                        raise ManifestValidationError(f"Result {index} {field} must be finite")
                except InvalidOperation as exc:
                    raise ManifestValidationError(f"Result {index} {field} must be a valid decimal string") from exc
        if not isinstance(result.get("verification_method"), str) or "arb" not in result["verification_method"].casefold():
            raise ManifestValidationError(f"Result {index} does not identify its Arb verification method")
        real_interval = result.get("real_enclosure")
        imag_interval = result.get("imag_enclosure")
        if bool(result.get("certified_interval")):
            _require_nonempty_text(real_interval, f"Result {index} real enclosure")
            _require_nonempty_text(imag_interval, f"Result {index} imaginary enclosure")
    assert first is not None and previous is not None

    claimed_start = exact_index(record.get("start_index"), "Record start_index")
    claimed_end = exact_index(record.get("end_index"), "Record end_index")
    if claimed_start != first:
        raise ManifestValidationError("Record start_index does not match its first computed result")
    if claimed_end != previous:
        raise ManifestValidationError("Record end_index does not match its last computed result")
    if len(statuses) != 1 or verification.get("status") not in statuses:
        raise ManifestValidationError("Research record mixes or misstates individual verification statuses")
    if verification.get("interval_verification") is not all(intervals):
        raise ManifestValidationError("Range-level interval-verification flag does not match its result records")
    _require_nonempty_text(record.get("submitted_at"), "Submission timestamp")
    _require_nonempty_text(record.get("contributor_id"), "Contributor identifier")
    return first, previous


def validate_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate integrity, exact indices, and consecutive accepted coverage."""
    if not isinstance(manifest, Mapping) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestValidationError("Global manifest has an unsupported schema version")
    if manifest.get("network_id") != "riemannsearch-global-research":
        raise ManifestValidationError("Global manifest has an unexpected network ID")
    if manifest.get("status") not in {"uninitialized", "initialized"}:
        raise ManifestValidationError("Global manifest status must be initialized or uninitialized")
    _verify_document_integrity(manifest, "Global manifest")
    accepted = manifest.get("accepted_ranges")
    history = manifest.get("publication_history")
    if not isinstance(accepted, list) or not isinstance(history, list):
        raise ManifestValidationError("Global manifest range and publication history fields must be arrays")

    if manifest["status"] == "uninitialized":
        if manifest.get("first_required_index") is not None or manifest.get("global_checkpoint_index") is not None:
            raise ManifestValidationError("An uninitialized network cannot claim an initial or completed index")
        if accepted or history:
            raise ManifestValidationError("An uninitialized network cannot contain published research")
        return {"initialized": False, "first_required_index": None, "checkpoint": None, "ranges": 0}

    first_required = exact_index(manifest.get("first_required_index"), "first_required_index")
    if not isinstance(manifest.get("initialized_at"), str) or not manifest["initialized_at"].strip():
        raise ManifestValidationError("Initialized manifest is missing initialized_at")
    cursor = first_required
    seen_paths = set()
    for number, item in enumerate(accepted, start=1):
        if not isinstance(item, dict):
            raise ManifestValidationError(f"Accepted range {number} must be an object")
        start = exact_index(item.get("start_index"), f"Range {number} start_index")
        end = exact_index(item.get("end_index"), f"Range {number} end_index")
        if start != cursor:
            raise ManifestValidationError(
                f"Accepted coverage has a gap or overlap before range {number}: expected {cursor}, got {start}"
            )
        if end < start:
            raise ManifestValidationError(f"Accepted range {number} ends before it starts")
        cursor = end + 1
        path = item.get("record_path")
        if not isinstance(path, str) or not path.startswith("data/ranges/") or ".." in Path(path).parts:
            raise ManifestValidationError(f"Accepted range {number} has an unsafe record path")
        if path in seen_paths:
            raise ManifestValidationError(f"Duplicate research record reference: {path}")
        seen_paths.add(path)
        digest = item.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ManifestValidationError(f"Accepted range {number} has an invalid record SHA-256")
        _require_nonempty_text(item.get("contributor_id"), f"Range {number} contributor_id")
        _require_nonempty_text(item.get("published_at"), f"Range {number} published_at")
        if item.get("verification_status") not in _ALLOWED_VERIFICATION:
            raise ManifestValidationError(f"Accepted range {number} has a non-eligible verification status")
    actual_checkpoint = str(cursor - 1) if accepted else None
    if manifest.get("global_checkpoint_index") != actual_checkpoint:
        raise ManifestValidationError("Global checkpoint does not equal the end of consecutive accepted records")
    if accepted and not history:
        raise ManifestValidationError("Published ranges must have corresponding publication history")
    return {
        "initialized": True,
        "first_required_index": first_required,
        "checkpoint": int(actual_checkpoint) if actual_checkpoint is not None else None,
        "next_index": cursor if cursor < BACKEND_INDEX_LIMIT else None,
        "ranges": len(accepted),
    }


def initial_manifest(first_required_index: int, *, initialized_at: Optional[str] = None) -> Dict[str, Any]:
    first = int(first_required_index)
    if first < 1 or first >= BACKEND_INDEX_LIMIT:
        raise ValueError("The initial research index is outside FLINT's supported indexed-zero range")
    timestamp = initialized_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return seal_document({
        "schema_version": SCHEMA_VERSION,
        "network_id": "riemannsearch-global-research",
        "status": "initialized",
        "initialized_at": timestamp,
        "first_required_index": str(first),
        "global_checkpoint_index": None,
        "accepted_ranges": [],
        "publication_history": [],
        "last_updated_at": None,
    })


def build_research_record(
    rows: Iterable[Mapping[str, Any]],
    experiment: Mapping[str, Any],
    contributor_id: str,
    *,
    submitted_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a shareable record from committed DB rows; never from a counter."""
    results: List[Dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: int(item["zero_index"])):
        results.append({
            "zero_index": str(int(row["zero_index"])),
            "real_part": str(row.get("real_part") or ""),
            "imag_part": str(row.get("imag_part") or ""),
            "residual": str(row.get("residual") or ""),
            "verification_residual": str(row.get("verification_residual") or ""),
            "precision_digits": int(row.get("precision") or 0),
            "verification_precision_digits": int(row.get("verification_precision") or 0),
            "verification_status": str(row.get("verification_status") or ""),
            "verification_method": str(row.get("verification_method") or experiment.get("verification_method") or ""),
            "real_enclosure": row.get("real_enclosure"),
            "imag_enclosure": row.get("imag_enclosure"),
            "certified_interval": bool(row.get("certified_interval")),
            "computed_at": str(row.get("created_at") or ""),
            # Text preserves the backend's recorded decimal and keeps canonical
            # integrity hashing stable across Python and browser JSON runtimes.
            "computation_time_ms": None if row.get("computation_time_ms") is None else str(row["computation_time_ms"]),
            "verification_time_ms": None if row.get("verification_time_ms") is None else str(row["verification_time_ms"]),
        })
    if not results:
        raise SubmissionRejectedError("This experiment has no committed results to publish")
    start = int(results[0]["zero_index"])
    end = int(results[-1]["zero_index"])
    method_values = {r["verification_method"] for r in results}
    if len(method_values) != 1:
        raise SubmissionRejectedError("The experiment mixes verification methods; export separate compatible ranges")
    verification_methods = method_values.pop()
    verification_statuses = {item["verification_status"] for item in results}
    if len(verification_statuses) != 1:
        raise SubmissionRejectedError("The experiment mixes verification statuses; export separate compatible ranges")
    verification_status = verification_statuses.pop()
    record = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "riemannsearch-zero-range",
        "start_index": str(start),
        "end_index": str(end),
        "computation": {
            "backend": str(experiment.get("backend") or ""),
            "backend_version": str(experiment.get("backend_version") or ""),
            "algorithm": str(experiment.get("algorithm") or ""),
            "precision_digits": max(item["precision_digits"] for item in results),
        },
        "verification": {
            "method": verification_methods,
            "precision_digits": max(item["verification_precision_digits"] for item in results),
            "status": verification_status,
            "interval_verification": all(item["certified_interval"] for item in results),
        },
        "contributor_id": str(contributor_id),
        "submitted_at": submitted_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "results": results,
    }
    return seal_document(record)


@dataclass(frozen=True)
class ImportedCheckpoint:
    manifest: Dict[str, Any]
    commit_sha: str
    branch: str
    published_at: Optional[str]
    contributor: Optional[str]
    fetched_at: str
    source: str = "live"
    record_files: Dict[str, bytes] = field(default_factory=dict)

    @property
    def state(self) -> Dict[str, Any]:
        return validate_manifest(self.manifest)

    @property
    def next_index(self) -> Optional[int]:
        state = self.state
        return state.get("next_index")


class GitHubResearchClient:
    """Read the exact public repo over HTTPS and validate every referenced range."""

    def __init__(
        self,
        *,
        opener: Optional[Callable[..., Any]] = None,
        timeout: float = 15.0,
        branch: Optional[str] = None,
    ):
        self._opener = opener or urllib.request.urlopen
        self.timeout = timeout
        self.branch = _validate_branch_name(branch)

    def _get(self, url: str) -> bytes:
        headers = {
            "User-Agent": "RiemannSearch/2.1",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with self._opener(request, timeout=self.timeout) as response:
                data = response.read(_MAX_DOCUMENT_BYTES + 1)
                if len(data) > _MAX_DOCUMENT_BYTES:
                    raise ResearchNetworkError("GitHub document exceeds the safe 16 MiB download limit")
                return data
        except urllib.error.HTTPError as exc:
            message = f"GitHub returned HTTP {exc.code}"
            if exc.code == 404:
                message += "; the repository or requested manifest/record is not published"
            elif exc.code == 401:
                message += "; authentication was rejected"
            elif exc.code == 403:
                message += "; access is denied or the API rate limit was reached"
            raise ResearchNetworkError(message) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResearchNetworkError(f"Could not reach the GitHub research repository: {exc}") from exc

    def _json(self, url: str) -> Any:
        return parse_json_bytes(self._get(url))

    @staticmethod
    def _verify_record_reference(reference: Mapping[str, Any], raw_record: bytes) -> None:
        """Recheck an immutable range file before trusting it from network or cache."""
        record_path = str(reference.get("record_path") or "")
        if not isinstance(raw_record, bytes) or len(raw_record) > _MAX_DOCUMENT_BYTES:
            raise ManifestValidationError(f"Published research record exceeds the safe 16 MiB limit: {record_path}")
        digest = hashlib.sha256(raw_record).hexdigest()
        if not hmac.compare_digest(digest, str(reference.get("sha256") or "")):
            raise ManifestValidationError(f"Published research record integrity check failed: {record_path}")
        record = parse_json_bytes(raw_record)
        start, end = validate_research_record(record)
        if start != int(reference["start_index"]) or end != int(reference["end_index"]):
            raise ManifestValidationError(f"Manifest range endpoints do not match {record_path}")
        if record.get("contributor_id") != reference.get("contributor_id"):
            raise ManifestValidationError(f"Manifest contributor does not match {record_path}")
        if record.get("verification", {}).get("status") != reference.get("verification_status"):
            raise ManifestValidationError(f"Manifest verification status does not match {record_path}")

    def fetch_latest_manifest(self, *, previous: Optional[ImportedCheckpoint] = None) -> ImportedCheckpoint:
        repo_info = self._json(f"{GITHUB_API}/repos/{REPOSITORY}")
        branch = self.branch or (repo_info.get("default_branch") if isinstance(repo_info, dict) else None)
        if not isinstance(branch, str) or not branch:
            raise ManifestMissingError("The GitHub repository has no published default branch yet")
        quoted_branch = urllib.parse.quote(branch, safe="")
        try:
            branch_ref = self._json(f"{GITHUB_API}/repos/{REPOSITORY}/git/ref/heads/{quoted_branch}")
        except ResearchNetworkError as exc:
            if "HTTP 404" in str(exc):
                raise ManifestMissingError("The GitHub repository is empty or has no published manifest") from exc
            raise
        head_sha = branch_ref.get("object", {}).get("sha")
        if not isinstance(head_sha, str) or not _GIT_SHA.fullmatch(head_sha):
            raise ManifestValidationError("GitHub returned an invalid repository commit SHA")
        query = urllib.parse.urlencode({"path": MANIFEST_PATH, "sha": head_sha, "per_page": 1})
        try:
            commits = self._json(f"{GITHUB_API}/repos/{REPOSITORY}/commits?{query}")
        except ResearchNetworkError as exc:
            if "HTTP 404" in str(exc):
                raise ManifestMissingError("The specified GitHub repository has no published global manifest") from exc
            raise
        if not isinstance(commits, list) or not commits:
            raise ManifestMissingError("The specified GitHub repository has no published global manifest")
        commit = commits[0]
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str) or not _GIT_SHA.fullmatch(commit_sha):
            raise ManifestValidationError("GitHub returned an invalid manifest commit SHA")
        if previous is not None and previous.branch == branch and previous.commit_sha == commit_sha:
            # Commit-SHA raw URLs are immutable. Reuse the previously validated
            # manifest and content-addressed range files after confirming the
            # public branch still points to the same manifest commit.
            try:
                validate_manifest(previous.manifest)
                if set(previous.record_files) != {
                    item["record_path"] for item in previous.manifest.get("accepted_ranges", [])
                }:
                    raise ManifestValidationError("Cached global range files do not match the manifest")
                for reference in previous.manifest.get("accepted_ranges", []):
                    self._verify_record_reference(reference, previous.record_files[reference["record_path"]])
            except (KeyError, TypeError, ValueError, ResearchNetworkError):
                previous = None
            if previous is not None:
                return replace(
                    previous,
                    fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                    source="live",
                )
        raw_base = f"{GITHUB_RAW}/{REPOSITORY}/{commit_sha}"
        try:
            raw_manifest = self._get(f"{raw_base}/{MANIFEST_PATH}")
        except ResearchNetworkError as exc:
            if "HTTP 404" in str(exc):
                raise ManifestMissingError("The manifest commit does not contain data/global_manifest.json") from exc
            raise
        manifest = parse_json_bytes(raw_manifest)
        state = validate_manifest(manifest)
        record_files: Dict[str, bytes] = {}
        for reference in manifest["accepted_ranges"]:
            record_path = reference["record_path"]
            raw_record = self._get(f"{raw_base}/{urllib.parse.quote(record_path, safe='/')}")
            self._verify_record_reference(reference, raw_record)
            record_files[record_path] = raw_record
        commit_meta = self._json(f"{GITHUB_API}/repos/{REPOSITORY}/commits/{commit_sha}")
        commit_data = commit_meta.get("commit", {}) if isinstance(commit_meta, dict) else {}
        author_data = commit_data.get("author", {}) if isinstance(commit_data, dict) else {}
        author = commit_meta.get("author", {}) if isinstance(commit_meta, dict) else {}
        return ImportedCheckpoint(
            manifest=copy.deepcopy(dict(manifest)),
            commit_sha=commit_sha,
            branch=branch,
            published_at=author_data.get("date"),
            contributor=(author.get("name") or author.get("login")),
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            record_files=record_files,
        )

    def save_cache(self, imported: ImportedCheckpoint, cache_path: Path) -> None:
        """Atomically save a validated snapshot, retaining provenance and fetch time."""
        validate_manifest(imported.manifest)
        payload = {
            "repository": REPOSITORY,
            "commit_sha": imported.commit_sha,
            "branch": imported.branch,
            "published_at": imported.published_at,
            "contributor": imported.contributor,
            "fetched_at": imported.fetched_at,
            "manifest": imported.manifest,
        }
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        record_cache = cache_path.parent / "global_research_records"
        for reference in imported.manifest.get("accepted_ranges", []):
            record_path = reference["record_path"]
            raw_record = imported.record_files.get(record_path)
            if raw_record is None:
                raise ManifestValidationError(f"Validated global record is missing from the import cache: {record_path}")
            digest = hashlib.sha256(raw_record).hexdigest()
            if not hmac.compare_digest(digest, reference["sha256"]):
                raise ManifestValidationError(f"Global record changed before local cache commit: {record_path}")
            self._verify_record_reference(reference, raw_record)
            record_cache.mkdir(parents=True, exist_ok=True)
            cached_record = record_cache / f"{digest}.json"
            if not cached_record.is_file():
                temporary_record = cached_record.with_name(cached_record.name + ".tmp")
                temporary_record.write_bytes(raw_record)
                os.replace(temporary_record, cached_record)
        temporary = cache_path.with_name(cache_path.name + ".tmp")
        temporary.write_bytes(serialize_document(payload))
        os.replace(temporary, cache_path)

    def load_cache(self, cache_path: Path) -> Optional[ImportedCheckpoint]:
        """Load cache for display only; caller must label it stale until live import."""
        path = Path(cache_path)
        if not path.is_file():
            return None
        try:
            if path.stat().st_size > _MAX_DOCUMENT_BYTES:
                return None
            payload = parse_json_bytes(path.read_bytes())
            if payload.get("repository") != REPOSITORY:
                raise ManifestValidationError("Cached checkpoint belongs to a different repository")
            manifest = payload.get("manifest")
            validate_manifest(manifest)
            record_files: Dict[str, bytes] = {}
            record_cache = path.parent / "global_research_records"
            for reference in manifest.get("accepted_ranges", []):
                digest = reference["sha256"]
                cached_record = record_cache / f"{digest}.json"
                if cached_record.stat().st_size > _MAX_DOCUMENT_BYTES:
                    return None
                raw_record = cached_record.read_bytes()
                self._verify_record_reference(reference, raw_record)
                record_files[reference["record_path"]] = raw_record
            if set(record_files) != {item["record_path"] for item in manifest.get("accepted_ranges", [])}:
                return None
            return ImportedCheckpoint(
                manifest=manifest,
                commit_sha=str(payload["commit_sha"]),
                branch=str(payload["branch"]),
                published_at=payload.get("published_at"),
                contributor=payload.get("contributor"),
                fetched_at=str(payload["fetched_at"]),
                source="cached",
                record_files=record_files,
            )
        except (OSError, KeyError, TypeError, ManifestValidationError):
            return None


def write_submission_file(record: Mapping[str, Any], path: Path) -> Path:
    validate_research_record(record)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(serialize_document(record))
    os.replace(temporary, destination)
    return destination
