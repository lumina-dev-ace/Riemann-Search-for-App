"""Optional GitHub App-backed contribution service.

Public synchronization stays in the desktop's unauthenticated GitHub reader.
This service accepts only authenticated, validated proposals and writes them
to review branches. It never updates the repository's default branch.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from research_network import (
    GITHUB_API,
    REPOSITORY,
    GitHubResearchClient,
    ManifestValidationError,
    ResearchNetworkError,
    exact_index,
    seal_document,
    serialize_document,
    validate_manifest,
    validate_research_record,
)


MAX_BODY_BYTES = 4 * 1024 * 1024
SESSION_TTL_SECONDS = 60 * 60
RATE_WINDOW_SECONDS = 60 * 60
MAX_SUBMISSIONS_PER_USER_PER_WINDOW = 5
MAX_SUBMISSIONS_PER_ADDRESS_PER_WINDOW = 20
USER_AGENT = "RiemannSearch-Contribution-Service/1.0"
API_VERSION = "2022-11-28"


class ServiceConfigurationError(RuntimeError):
    """Raised if server-side GitHub App secrets or settings are unavailable."""


@dataclass(frozen=True)
class Settings:
    github_app_client_id: str = ""
    github_app_id: str = ""
    github_installation_id: str = ""
    github_private_key: str = ""
    session_signing_key: str = ""
    rate_limit_database: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        private_key = os.environ.get("RIEMANNSEARCH_GITHUB_APP_PRIVATE_KEY", "")
        key_path = os.environ.get("RIEMANNSEARCH_GITHUB_APP_PRIVATE_KEY_PATH", "")
        if not private_key and key_path:
            try:
                private_key = Path(key_path).read_text(encoding="utf-8")
            except OSError:
                private_key = ""
        return cls(
            github_app_client_id=os.environ.get("RIEMANNSEARCH_GITHUB_APP_CLIENT_ID", "").strip(),
            github_app_id=os.environ.get("RIEMANNSEARCH_GITHUB_APP_ID", "").strip(),
            github_installation_id=os.environ.get("RIEMANNSEARCH_GITHUB_INSTALLATION_ID", "").strip(),
            github_private_key=private_key,
            session_signing_key=os.environ.get("RIEMANNSEARCH_SESSION_SIGNING_KEY", ""),
            rate_limit_database=os.environ.get(
                "RIEMANNSEARCH_RATE_LIMIT_DATABASE", "./contribution-service.sqlite3"
            ),
        )

    @property
    def enabled(self) -> bool:
        return bool(
            self.github_app_client_id
            and self.github_app_id
            and self.github_installation_id
            and self.github_private_key
            and len(self.session_signing_key.encode("utf-8")) >= 32
            and self.rate_limit_database
        )


class SQLiteRateLimiter:
    """Durable fixed-window rate limiting for one persistent service instance."""

    def __init__(self, database_path: str, key_salt: bytes):
        if not database_path:
            raise ValueError("A persistent rate-limit database path is required")
        self.path = Path(database_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.key_salt = key_salt
        with closing(self._connect()) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rate_buckets ("
                "fingerprint TEXT NOT NULL, window_start INTEGER NOT NULL, count INTEGER NOT NULL, "
                "PRIMARY KEY (fingerprint, window_start))"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def allow(self, key: str, limit: int, window_seconds: int = RATE_WINDOW_SECONDS) -> bool:
        now = int(time.time())
        bucket = now // window_seconds * window_seconds
        fingerprint = hmac.new(self.key_salt, key.encode("utf-8"), hashlib.sha256).hexdigest()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM rate_buckets WHERE window_start < ?", (now - 2 * 86400,))
            row = connection.execute(
                "SELECT count FROM rate_buckets WHERE fingerprint=? AND window_start=?",
                (fingerprint, bucket),
            ).fetchone()
            count = int(row[0]) if row else 0
            if count >= limit:
                connection.execute("COMMIT")
                return False
            connection.execute(
                "INSERT INTO rate_buckets(fingerprint, window_start, count) VALUES(?,?,1) "
                "ON CONFLICT(fingerprint, window_start) DO UPDATE SET count=count+1",
                (fingerprint, bucket),
            )
            connection.execute("COMMIT")
            return True


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class SessionSigner:
    def __init__(self, signing_key: str, ttl_seconds: int = SESSION_TTL_SECONDS):
        key = signing_key.encode("utf-8")
        if len(key) < 32:
            raise ValueError("The contribution session signing key must be at least 32 bytes")
        self.key = key
        self.ttl_seconds = int(ttl_seconds)

    def issue(self, user_id: int, login: str, now: Optional[int] = None) -> str:
        issued = int(time.time() if now is None else now)
        payload = {
            "iss": "riemannsearch-contribution-service",
            "sub": str(int(user_id)),
            "login": str(login),
            "iat": issued,
            "exp": issued + self.ttl_seconds,
            "jti": secrets.token_urlsafe(16),
        }
        header = _b64url(b'{"alg":"HS256","typ":"JWT"}')
        body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        signed = f"{header}.{body}"
        signature = _b64url(hmac.new(self.key, signed.encode("ascii"), hashlib.sha256).digest())
        return f"{signed}.{signature}"

    def verify(self, token: str, now: Optional[int] = None) -> dict[str, Any]:
        try:
            header, body, signature = token.split(".")
            signed = f"{header}.{body}"
            expected = _b64url(hmac.new(self.key, signed.encode("ascii"), hashlib.sha256).digest())
            if not hmac.compare_digest(expected, signature):
                raise ValueError
            decoded = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
            payload = json.loads(decoded)
            current = int(time.time() if now is None else now)
            if payload.get("iss") != "riemannsearch-contribution-service" or int(payload.get("exp", 0)) <= current:
                raise ValueError
            if not str(payload.get("sub", "")).isdigit() or not str(payload.get("login", "")):
                raise ValueError
            return payload
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError("Contribution session is invalid or expired") from exc


class GitHubApi:
    def __init__(self, opener: Optional[Callable[..., Any]] = None):
        self.opener = opener or urllib.request.urlopen

    def request(self, method: str, path: str, token: Optional[str], body: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if body is not None else None
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "Content-Type": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{GITHUB_API}{path}", data=raw, method=method,
            headers=headers,
        )
        try:
            with self.opener(request, timeout=20) as response:
                result = response.read(8 * 1024 * 1024 + 1)
            if len(result) > 8 * 1024 * 1024:
                raise ResearchNetworkError("GitHub returned a response larger than the service limit")
            return json.loads(result) if result else {}
        except urllib.error.HTTPError as exc:
            if exc.code in (409, 422):
                raise SubmissionConflict("GitHub rejected a stale or duplicate proposal branch") from exc
            if exc.code in (401, 403):
                raise ServiceConfigurationError("The GitHub App installation is missing required repository permissions") from exc
            raise ResearchNetworkError(f"GitHub proposal service returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ResearchNetworkError("Could not reach the GitHub proposal service") from exc


class SubmissionConflict(ResearchNetworkError):
    """A stale, duplicate, or already-open proposal conflicts with this range."""


class InstallationTokenProvider:
    def __init__(self, settings: Settings, api: GitHubApi):
        self.settings = settings
        self.api = api
        self._token = ""
        self._expires_at = 0
        self._lock = threading.Lock()

    def get(self, repository_id: int) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at - 60:
                return self._token
            now = int(time.time())
            app_jwt = jwt.encode(
                {"iat": now - 30, "exp": now + 8 * 60, "iss": self.settings.github_app_id},
                self.settings.github_private_key,
                algorithm="RS256",
            )
            result = self.api.request(
                "POST",
                f"/app/installations/{urllib.parse.quote(self.settings.github_installation_id, safe='')}/access_tokens",
                app_jwt,
                {
                    "repository_ids": [int(repository_id)],
                    "permissions": {"contents": "write", "pull_requests": "write"},
                },
            )
            token = result.get("token")
            expires = result.get("expires_at")
            if not isinstance(token, str) or not token or not isinstance(expires, str):
                raise ServiceConfigurationError("GitHub did not issue a repository-scoped installation token")
            try:
                expiry = datetime.fromisoformat(expires.replace("Z", "+00:00")).timestamp()
            except ValueError as exc:
                raise ServiceConfigurationError("GitHub returned an invalid installation-token expiry") from exc
            self._token, self._expires_at = token, expiry
            return token


class GitHubProposalPublisher:
    """Create a validated commit and pull request using the server-side App."""

    def __init__(self, settings: Settings, api: Optional[GitHubApi] = None, public_reader=None):
        self.settings = settings
        self.api = api or GitHubApi()
        self.public_reader = public_reader or GitHubResearchClient()
        self.installation_tokens = InstallationTokenProvider(settings, self.api)

    def _app_request(self, method: str, path: str, body=None, repository_id: Optional[int] = None):
        if repository_id is None:
            repository_id = self.api.request("GET", f"/repos/{REPOSITORY}", None).get("id")
        if not isinstance(repository_id, int):
            raise ServiceConfigurationError("The contribution repository identity could not be resolved")
        return self.api.request(method, path, self.installation_tokens.get(repository_id), body)

    def submit(self, untrusted_record: Mapping[str, Any], contributor: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(untrusted_record, Mapping):
            raise ManifestValidationError("A research-range JSON object is required")
        imported = self.public_reader.fetch_latest_manifest()
        manifest = imported.manifest
        state = validate_manifest(manifest)
        expected = state.get("next_index")
        if expected is None:
            raise SubmissionConflict("The global network has not been initialized by its maintainers")

        record = dict(untrusted_record)
        record["contributor_id"] = str(contributor["login"])
        record["submitted_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        record.pop("integrity", None)
        record = seal_document(record)
        start, end = validate_research_record(record)
        if start != expected:
            raise SubmissionConflict(
                f"This proposal begins at {start:,}; the current network requires {expected:,}. Import the latest checkpoint."
            )

        repo_meta = self.api.request("GET", f"/repos/{REPOSITORY}", None)
        repo_id = repo_meta.get("id")
        owner = (repo_meta.get("owner") or {}).get("login")
        branch = repo_meta.get("default_branch")
        if not isinstance(repo_id, int) or not isinstance(owner, str) or not isinstance(branch, str):
            raise ServiceConfigurationError("The configured repository metadata is invalid")
        refs_before = self.api.request(
            "GET", f"/repos/{REPOSITORY}/git/ref/heads/{urllib.parse.quote(branch, safe='')}", None
        )
        head_sha = (refs_before.get("object") or {}).get("sha")
        if not isinstance(head_sha, str) or len(head_sha) not in (40, 64):
            raise ResearchNetworkError("GitHub returned an invalid repository head")
        refs_after = self.api.request(
            "GET", f"/repos/{REPOSITORY}/git/ref/heads/{urllib.parse.quote(branch, safe='')}", None
        )
        if ((refs_after.get("object") or {}).get("sha")) != head_sha:
            raise SubmissionConflict("The global repository changed during validation. Import and resubmit.")

        record_bytes = serialize_document(record)
        record_sha = hashlib.sha256(record_bytes).hexdigest()
        record_path = f"data/ranges/zero-{start}-{end}-{record_sha[:16]}.json"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        manifest = json.loads(json.dumps(manifest))
        manifest.pop("integrity", None)
        manifest["accepted_ranges"].append({
            "start_index": str(start), "end_index": str(end), "record_path": record_path,
            "sha256": record_sha, "verification_status": record["verification"]["status"],
            "contributor_id": str(contributor["login"]), "published_at": now,
        })
        manifest["global_checkpoint_index"] = str(end)
        manifest["last_updated_at"] = now
        manifest["publication_history"].append({
            "published_at": now, "start_index": str(start), "end_index": str(end),
            "record_path": record_path, "contributor_id": str(contributor["login"]),
        })
        manifest = seal_document(manifest)
        validate_manifest(manifest)
        manifest_bytes = serialize_document(manifest)

        marker = f"<!-- riemannsearch-range:{start}:{end}:{record_sha} -->"
        branch_name = f"riemannsearch/contribution-{start}-{end}-{record_sha[:12]}"
        existing = self.api.request(
            "GET",
            f"/repos/{REPOSITORY}/pulls?state=open&head={urllib.parse.quote(owner + ':' + branch_name, safe='')}&per_page=1",
            None,
        )
        if isinstance(existing, list) and existing:
            return {"url": existing[0].get("html_url"), "branch": branch_name, "already_open": True}

        base_commit = self._app_request("GET", f"/repos/{REPOSITORY}/git/commits/{head_sha}", repository_id=repo_id)
        base_tree = (base_commit.get("tree") or {}).get("sha")
        if not isinstance(base_tree, str):
            raise ResearchNetworkError("GitHub did not return the base tree")
        record_blob = self._app_request("POST", f"/repos/{REPOSITORY}/git/blobs", {
            "content": base64.b64encode(record_bytes).decode("ascii"), "encoding": "base64",
        }, repo_id)
        manifest_blob = self._app_request("POST", f"/repos/{REPOSITORY}/git/blobs", {
            "content": base64.b64encode(manifest_bytes).decode("ascii"), "encoding": "base64",
        }, repo_id)
        tree = self._app_request("POST", f"/repos/{REPOSITORY}/git/trees", {
            "base_tree": base_tree,
            "tree": [
                {"path": record_path, "mode": "100644", "type": "blob", "sha": record_blob.get("sha")},
                {"path": "data/global_manifest.json", "mode": "100644", "type": "blob", "sha": manifest_blob.get("sha")},
            ],
        }, repo_id)
        commit = self._app_request("POST", f"/repos/{REPOSITORY}/git/commits", {
            "message": f"Propose verified zero range {start}-{end}",
            "tree": tree.get("sha"), "parents": [head_sha],
        }, repo_id)
        commit_sha = commit.get("sha")
        if not isinstance(commit_sha, str):
            raise ResearchNetworkError("GitHub did not create the proposal commit")

        try:
            self._app_request("POST", f"/repos/{REPOSITORY}/git/refs", {
                "ref": "refs/heads/" + branch_name, "sha": commit_sha,
            }, repo_id)
            pull = self._app_request("POST", f"/repos/{REPOSITORY}/pulls", {
                "title": f"Research proposal: verified zeros {start}–{end}",
                "head": owner + ":" + branch_name,
                "base": branch,
                "body": (
                    f"Validated RiemannSearch contribution from `{contributor['login']}` for indices "
                    f"`{start}`–`{end}`.\n\n{marker}\n\n"
                    "The service validated schema, exact sequence, stored Arb metadata, and checksums. "
                    "Those checks do not independently recompute the zeta zeros or prove the Riemann Hypothesis. "
                    "Maintainer review and repository checks are required before merge."
                ),
            }, repo_id)
        except Exception:
            try:
                self._app_request(
                    "DELETE", f"/repos/{REPOSITORY}/git/refs/heads/{urllib.parse.quote(branch_name, safe='/')}",
                    repository_id=repo_id,
                )
            except Exception:
                pass
            raise
        return {"url": pull.get("html_url"), "branch": branch_name, "already_open": False}


def _bearer(request: Request) -> str:
    value = request.headers.get("Authorization", "")
    if not value.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Contributor sign-in is required")
    return value[7:].strip()


def create_app(
    settings: Optional[Settings] = None,
    *,
    github_api: Optional[GitHubApi] = None,
    rate_limiter: Optional[SQLiteRateLimiter] = None,
    publisher: Optional[GitHubProposalPublisher] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="RiemannSearch Contribution Service", version="1.0.0", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.github_api = github_api or GitHubApi()
    app.state.rate_limiter = rate_limiter
    app.state.publisher = publisher
    app.state.signer = SessionSigner(settings.session_signing_key) if len(settings.session_signing_key.encode("utf-8")) >= 32 else None
    if settings.enabled and app.state.rate_limiter is None:
        app.state.rate_limiter = SQLiteRateLimiter(
            settings.rate_limit_database, settings.session_signing_key.encode("utf-8")
        )
    if settings.enabled and app.state.publisher is None:
        app.state.publisher = GitHubProposalPublisher(settings, app.state.github_api)

    @app.middleware("http")
    async def request_size_limit(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return JSONResponse({"detail": "Request exceeds the 4 MiB contribution limit"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
        return await call_next(request)

    def require_enabled():
        if not settings.enabled or app.state.signer is None:
            raise HTTPException(status_code=503, detail="Optional contribution service is not configured")

    def limit(key: str, amount: int):
        limiter = app.state.rate_limiter
        if limiter is None:
            raise HTTPException(status_code=503, detail="Persistent abuse protection is not configured")
        if not limiter.allow(key, amount):
            raise HTTPException(status_code=429, detail="Contribution service rate limit reached; retry later")

    @app.get("/health")
    def health():
        return {"status": "ok", "contributions_enabled": bool(settings.enabled)}

    @app.get("/v1/config")
    def public_config():
        return {
            "repository": REPOSITORY,
            "contributions_enabled": bool(settings.enabled),
            "github_app_client_id": settings.github_app_client_id if settings.enabled else None,
            "authorization_url": "https://github.com/login/device",
            "session_ttl_seconds": SESSION_TTL_SECONDS,
        }

    @app.post("/v1/session")
    async def exchange_session(request: Request):
        require_enabled()
        ip = request.client.host if request.client else "unknown"
        limit("session-ip:" + ip, MAX_SUBMISSIONS_PER_ADDRESS_PER_WINDOW)
        try:
            body = await request.body()
            if len(body) > 16 * 1024:
                raise HTTPException(status_code=413, detail="Sign-in request is too large")
            payload = json.loads(body)
            access_token = payload.get("github_user_access_token") if isinstance(payload, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid sign-in request")
        if not isinstance(access_token, str) or not access_token.startswith("ghu_"):
            raise HTTPException(status_code=401, detail="A GitHub App user authorization is required")
        try:
            user = app.state.github_api.request("GET", "/user", access_token)
        except Exception:
            raise HTTPException(status_code=401, detail="GitHub did not accept the contributor sign-in")
        user_id, login = user.get("id"), user.get("login")
        if type(user_id) is not int or not isinstance(login, str) or not login:
            raise HTTPException(status_code=401, detail="GitHub returned an invalid contributor identity")
        session = app.state.signer.issue(user_id, login)
        return {"session_token": session, "login": login, "expires_in": SESSION_TTL_SECONDS}

    @app.post("/v1/contributions")
    async def submit_contribution(request: Request):
        require_enabled()
        ip = request.client.host if request.client else "unknown"
        try:
            session = app.state.signer.verify(_bearer(request))
        except ValueError:
            raise HTTPException(status_code=401, detail="Contributor session is invalid or expired")
        limit("submit-ip:" + ip, MAX_SUBMISSIONS_PER_ADDRESS_PER_WINDOW)
        limit("submit-user:" + session["sub"], MAX_SUBMISSIONS_PER_USER_PER_WINDOW)
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Contribution exceeds the 4 MiB request limit")
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid contribution JSON")
        if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
            raise HTTPException(status_code=400, detail="A research-range record is required")
        if app.state.publisher is None:
            raise HTTPException(status_code=503, detail="GitHub App proposal publishing is not configured")
        try:
            from starlette.concurrency import run_in_threadpool
            result = await run_in_threadpool(
                app.state.publisher.submit, payload["record"],
                {"id": int(session["sub"]), "login": session["login"]},
            )
        except SubmissionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except ManifestValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except ServiceConfigurationError:
            raise HTTPException(status_code=503, detail="The repository contribution service is temporarily unavailable")
        except ResearchNetworkError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        return {"status": "proposal_created", **result}

    return app


app = create_app()
