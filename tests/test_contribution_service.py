from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from research_network import initial_manifest, seal_document
from services.contribution_api.app import (
    GitHubApi,
    GitHubProposalPublisher,
    SQLiteRateLimiter,
    SessionSigner,
    Settings,
    SubmissionConflict,
    create_app,
)


FIRST = 10_000_000_000_000


def valid_record(start: int = FIRST) -> dict:
    return seal_document({
        "schema_version": 1,
        "record_type": "riemannsearch-zero-range",
        "start_index": str(start),
        "end_index": str(start),
        "computation": {
            "backend": "python-flint/Arb",
            "backend_version": "test fixture",
            "algorithm": "indexed zeta zero batch",
            "precision_digits": 160,
        },
        "verification": {
            "method": "FLINT/Arb interval recheck",
            "precision_digits": 320,
            "status": "certified_interval_rechecked",
            "interval_verification": True,
        },
        "contributor_id": "untrusted-local-label",
        "submitted_at": "2026-11-13T00:00:00Z",
        "results": [{
            "zero_index": str(start),
            "real_part": "0.5",
            "imag_part": "100.0",
            "residual": "1e-100",
            "verification_residual": "1e-200",
            "precision_digits": 160,
            "verification_precision_digits": 320,
            "verification_status": "certified_interval_rechecked",
            "verification_method": "FLINT/Arb interval recheck",
            "real_enclosure": "[0.5 +/- 1e-300]",
            "imag_enclosure": "[100 +/- 1e-300]",
            "certified_interval": True,
            "computed_at": "2026-11-13T00:00:00Z",
            "computation_time_ms": "1.0",
            "verification_time_ms": "1.0",
        }],
    })


class FakeLimiter:
    def __init__(self, allow=True):
        self.allow_result = allow
        self.calls = []

    def allow(self, key, limit, window_seconds=3600):
        self.calls.append((key, limit, window_seconds))
        return self.allow_result


class FakeGitHubApi:
    def __init__(self):
        self.calls = []

    def request(self, method, path, token, body=None):
        self.calls.append((method, path, token, body))
        if method == "POST" and path.endswith("/access_tokens"):
            expires = (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat().replace("+00:00", "Z")
            return {"token": "installation-token", "expires_at": expires}
        if method == "GET" and path == "/repos/lumina-dev-ace/Riemann-Search-for-App":
            return {"id": 731, "owner": {"login": "lumina-dev-ace"}, "default_branch": "main"}
        if method == "GET" and path.endswith("/git/ref/heads/main"):
            return {"object": {"sha": "a" * 40}}
        if method == "GET" and path.endswith("/git/commits/" + "a" * 40):
            return {"tree": {"sha": "b" * 40}}
        if method == "GET" and "/pulls?" in path:
            return []
        if method == "POST" and path.endswith("/git/blobs"):
            return {"sha": "c" * 40 if len([x for x in self.calls if x[1].endswith("/git/blobs")]) == 1 else "d" * 40}
        if method == "POST" and path.endswith("/git/trees"):
            return {"sha": "e" * 40}
        if method == "POST" and path.endswith("/git/commits"):
            return {"sha": "f" * 40}
        if method == "POST" and path.endswith("/git/refs"):
            return {}
        if method == "POST" and path.endswith("/pulls"):
            return {"html_url": "https://github.com/lumina-dev-ace/Riemann-Search-for-App/pull/999"}
        raise AssertionError(f"Unexpected GitHub API request: {method} {path}")


class FakeReader:
    def __init__(self, manifest=None):
        self.manifest = manifest or initial_manifest(FIRST, initialized_at="2026-11-14T00:00:00Z")

    def fetch_latest_manifest(self):
        from research_network import ImportedCheckpoint
        return ImportedCheckpoint(self.manifest, "a" * 40, "main", None, None, "2026-11-14T00:00:00Z")


class FakePublisher:
    def __init__(self):
        self.calls = []

    def submit(self, record, contributor):
        self.calls.append((record, contributor))
        return {"url": "https://github.com/example/pull/1", "branch": "riemannsearch/contribution-test"}


class ContributionServiceTests(unittest.TestCase):
    def settings(self, database_path="/tmp/contribution-tests.sqlite3"):
        return Settings(
            github_app_client_id="Iv1.test-client",
            github_app_id="123",
            github_installation_id="456",
            github_private_key="test-only-not-used",
            session_signing_key="s" * 48,
            rate_limit_database=database_path,
        )

    def test_public_service_config_requires_no_sign_in(self):
        app = create_app(Settings())
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").json(), {"status": "ok", "contributions_enabled": False})
            config = client.get("/v1/config").json()
            self.assertEqual(config["repository"], "lumina-dev-ace/Riemann-Search-for-App")
            self.assertFalse(config["contributions_enabled"])

    def test_optional_session_exchange_and_proposal_require_github_app_sign_in(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.settings(str(Path(directory) / "rate.sqlite3"))
            api = FakeGitHubApi()
            api.request = lambda method, path, token, body=None: (
                {"id": 42, "login": "researcher"}
                if method == "GET" and path == "/user" and token == "ghu_test_access"
                else (_ for _ in ()).throw(AssertionError((method, path, token)))
            )
            limiter = FakeLimiter()
            publisher = FakePublisher()
            app = create_app(settings, github_api=api, rate_limiter=limiter, publisher=publisher)
            with TestClient(app) as client:
                self.assertEqual(client.post("/v1/contributions", json={"record": valid_record()}).status_code, 401)
                bad = client.post("/v1/session", json={"github_user_access_token": "ghp_not_a_user_token"})
                self.assertEqual(bad.status_code, 401)
                signed_in = client.post("/v1/session", json={"github_user_access_token": "ghu_test_access"})
                self.assertEqual(signed_in.status_code, 200)
                payload = signed_in.json()
                self.assertEqual(payload["login"], "researcher")
                self.assertNotIn("ghu_test_access", signed_in.text)
                result = client.post(
                    "/v1/contributions",
                    headers={"Authorization": "Bearer " + payload["session_token"]},
                    json={"record": valid_record()},
                )
                self.assertEqual(result.status_code, 200)
                self.assertEqual(result.json()["status"], "proposal_created")
                self.assertEqual(publisher.calls[0][1], {"id": 42, "login": "researcher"})
                self.assertTrue(any(call[0].startswith("submit-user:") for call in limiter.calls))

    def test_rate_limit_denial_and_oversized_submission_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.settings(str(Path(directory) / "rate.sqlite3"))
            api = FakeGitHubApi()
            api.request = lambda method, path, token, body=None: {"id": 42, "login": "researcher"}
            limiter = FakeLimiter(allow=False)
            app = create_app(settings, github_api=api, rate_limiter=limiter, publisher=FakePublisher())
            with TestClient(app) as client:
                self.assertEqual(client.post("/v1/session", json={"github_user_access_token": "ghu_test"}).status_code, 429)

            limiter = FakeLimiter()
            app = create_app(settings, github_api=api, rate_limiter=limiter, publisher=FakePublisher())
            signer = app.state.signer
            token = signer.issue(42, "researcher")
            with TestClient(app) as client:
                response = client.post(
                    "/v1/contributions",
                    headers={"Authorization": "Bearer " + token},
                    content=b"{" + b" " * (4 * 1024 * 1024) + b"}",
                )
                self.assertEqual(response.status_code, 413)

    def test_sessions_are_signed_expiring_and_not_personal_tokens(self):
        signer = SessionSigner("k" * 48, ttl_seconds=60)
        token = signer.issue(8, "user", now=100)
        claims = signer.verify(token, now=159)
        self.assertEqual(claims["sub"], "8")
        self.assertEqual(claims["login"], "user")
        with self.assertRaises(ValueError):
            signer.verify(token, now=160)
        with self.assertRaises(ValueError):
            signer.verify(token + "x", now=101)

    def test_sqlite_rate_limiter_is_persistent_and_separates_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "rate.sqlite3")
            first = SQLiteRateLimiter(path, b"r" * 32)
            self.assertTrue(first.allow("user:42", 1))
            self.assertFalse(first.allow("user:42", 1))
            second = SQLiteRateLimiter(path, b"r" * 32)
            self.assertFalse(second.allow("user:42", 1))
            self.assertTrue(second.allow("ip:127.0.0.1", 1))

    def test_github_app_proposal_updates_only_review_branch_not_main(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = self.settings(str(Path(directory) / "rate.sqlite3"))
            api = FakeGitHubApi()
            reader = FakeReader()
            publisher = GitHubProposalPublisher(settings, api=api, public_reader=reader)
            with patch("services.contribution_api.app.jwt.encode", return_value="app-jwt"):
                result = publisher.submit(valid_record(), {"id": 42, "login": "researcher"})
            self.assertTrue(result["url"].endswith("/pull/999"))
            methods = [(method, path) for method, path, _token, _body in api.calls]
            self.assertIn(("POST", "/repos/lumina-dev-ace/Riemann-Search-for-App/git/refs"), methods)
            self.assertIn(("POST", "/repos/lumina-dev-ace/Riemann-Search-for-App/pulls"), methods)
            self.assertFalse(any(method == "PATCH" for method, _ in methods))
            ref_body = next(body for method, path, _token, body in api.calls if method == "POST" and path.endswith("/git/refs"))
            self.assertTrue(ref_body["ref"].startswith("refs/heads/riemannsearch/contribution-"))
            token_request = next(body for method, path, _token, body in api.calls if path.endswith("/access_tokens"))
            self.assertEqual(token_request["repository_ids"], [731])
            self.assertEqual(token_request["permissions"], {"contents": "write", "pull_requests": "write"})

    def test_stale_or_nonconsecutive_record_is_rejected_before_any_write(self):
        api = FakeGitHubApi()
        publisher = GitHubProposalPublisher(self.settings(), api=api, public_reader=FakeReader())
        with self.assertRaises(SubmissionConflict):
            publisher.submit(valid_record(FIRST + 1), {"id": 42, "login": "researcher"})
        self.assertFalse(any(method == "POST" for method, _path, _token, _body in api.calls))


if __name__ == "__main__":
    unittest.main()
