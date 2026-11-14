from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from research_network import (
    GitHubResearchClient,
    ManifestMissingError,
    ManifestValidationError,
    ResearchNetworkError,
    initial_manifest,
    parse_json_bytes,
    seal_document,
    serialize_document,
    validate_manifest,
    validate_research_record,
)


FIRST = 10_000_000_000_000
COMMIT = "a" * 40


def valid_record(start: int = FIRST, count: int = 2, contributor: str = "researcher"):
    results = []
    for index in range(start, start + count):
        results.append({
            "zero_index": str(index),
            "real_part": "0.5",
            "imag_part": f"123.456{index % 10}",
            "residual": "1e-120",
            "verification_residual": "1e-310",
            "precision_digits": 160,
            "verification_precision_digits": 320,
            "verification_status": "certified_interval_rechecked",
            "verification_method": "FLINT/Arb interval recheck",
            "real_enclosure": "[0.5 +/- 1e-300]",
            "imag_enclosure": "[123.456 +/- 1e-300]",
            "certified_interval": True,
            "computed_at": "2026-11-13T00:00:00Z",
            "computation_time_ms": "10.5",
            "verification_time_ms": "2.5",
        })
    return seal_document({
        "schema_version": 1,
        "record_type": "riemannsearch-zero-range",
        "start_index": str(start),
        "end_index": str(start + count - 1),
        "computation": {
            "backend": "python-flint/Arb",
            "backend_version": "0.9.0 / 3.6.0",
            "algorithm": "indexed zeta zero batch",
            "precision_digits": 160,
        },
        "verification": {
            "method": "FLINT/Arb interval recheck",
            "precision_digits": 320,
            "status": "certified_interval_rechecked",
            "interval_verification": True,
        },
        "contributor_id": contributor,
        "submitted_at": "2026-11-13T00:00:00Z",
        "results": results,
    })


def manifest_with_range(record=None, first=FIRST):
    record = record or valid_record(first)
    record_bytes = serialize_document(record)
    start, end = validate_research_record(record)
    path = f"data/ranges/test-{start}-{end}.json"
    base = initial_manifest(first, initialized_at="2026-11-13T00:00:00Z")
    base.pop("integrity")
    base["accepted_ranges"] = [{
        "start_index": str(start), "end_index": str(end), "record_path": path,
        "sha256": hashlib.sha256(record_bytes).hexdigest(),
        "verification_status": record["verification"]["status"],
        "contributor_id": record["contributor_id"], "published_at": record["submitted_at"],
    }]
    base["global_checkpoint_index"] = str(end)
    base["publication_history"] = [{
        "published_at": record["submitted_at"], "start_index": str(start),
        "end_index": str(end), "record_path": path, "contributor_id": record["contributor_id"],
    }]
    return seal_document(base), path, record_bytes


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body if size < 0 else self.body[:size]


class FakeOpener:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []
        self.requests = []

    def __call__(self, request, timeout):
        url = request.full_url
        self.urls.append(url)
        self.requests.append(request)
        if url not in self.responses:
            raise AssertionError(f"Unexpected GitHub request: {url}")
        value = self.responses[url]
        if isinstance(value, Exception):
            raise value
        return FakeResponse(value if isinstance(value, bytes) else json.dumps(value).encode("utf-8"))


class ResearchNetworkTests(unittest.TestCase):
    def test_initial_manifest_keeps_approved_boundary_separate_from_completed_checkpoint(self):
        manifest = initial_manifest(FIRST, initialized_at="2026-11-13T00:00:00Z")
        state = validate_manifest(manifest)
        self.assertTrue(state["initialized"])
        self.assertEqual(state["first_required_index"], FIRST)
        self.assertIsNone(state["checkpoint"])
        self.assertEqual(state["next_index"], FIRST)
        uninitialized = initial_manifest(FIRST)
        uninitialized.update({"status": "uninitialized", "initialized_at": None, "first_required_index": None})
        uninitialized = seal_document(uninitialized)
        self.assertFalse(validate_manifest(uninitialized)["initialized"])
        self.assertIsNone(uninitialized["global_checkpoint_index"])

    def test_record_hash_metadata_and_exact_large_indices_validate(self):
        record = valid_record()
        self.assertEqual(validate_research_record(record), (FIRST, FIRST + 1))
        changed = copy.deepcopy(record)
        changed["results"][1]["zero_index"] = str(FIRST + 2)
        changed = seal_document(changed)
        with self.assertRaisesRegex(ManifestValidationError, "not consecutive"):
            validate_research_record(changed)

        invalid_timing = valid_record(count=1)
        invalid_timing["results"][0]["computation_time_ms"] = 10.5
        with self.assertRaisesRegex(ManifestValidationError, "decimal string"):
            validate_research_record(seal_document(invalid_timing))

        fabricated_endpoint = valid_record(count=1)
        fabricated_endpoint["end_index"] = str(FIRST + 1)
        with self.assertRaisesRegex(ManifestValidationError, "end_index"):
            validate_research_record(seal_document(fabricated_endpoint))

    def test_failed_verification_cannot_enter_a_publishable_range(self):
        record = valid_record(count=1)
        record["results"][0]["verification_status"] = "failed"
        record = seal_document(record)
        with self.assertRaisesRegex(ManifestValidationError, "not an eligible"):
            validate_research_record(record)

    def test_manifest_rejects_gap_overlap_and_fabricated_endpoint(self):
        manifest = initial_manifest(FIRST, initialized_at="2026-11-13T00:00:00Z")
        manifest.pop("integrity")
        manifest["accepted_ranges"] = [
            {"start_index": str(FIRST + 1), "end_index": str(FIRST + 2), "record_path": "data/ranges/a.json", "sha256": "a" * 64, "verification_status": "certified_interval_rechecked", "contributor_id": "x", "published_at": "now"}
        ]
        manifest["global_checkpoint_index"] = str(FIRST + 2)
        manifest["publication_history"] = [{}]
        manifest = seal_document(manifest)
        with self.assertRaisesRegex(ManifestValidationError, "gap or overlap"):
            validate_manifest(manifest)

        good, _, _ = manifest_with_range()
        good["global_checkpoint_index"] = str(FIRST + 9)
        good = seal_document(good)
        with self.assertRaisesRegex(ManifestValidationError, "does not equal"):
            validate_manifest(good)

    def test_public_import_verifies_range_hash_and_cache_without_authentication(self):
        manifest, record_path, record_bytes = manifest_with_range()
        raw_base = f"https://raw.githubusercontent.com/lumina-dev-ace/Riemann-Search-for-App/{COMMIT}"
        responses = {
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App": {"default_branch": "main"},
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/git/ref/heads/main": {"object": {"sha": "b" * 40}},
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/commits?path=data%2Fglobal_manifest.json&sha=" + "b" * 40 + "&per_page=1": [{"sha": COMMIT}],
            f"{raw_base}/data/global_manifest.json": serialize_document(manifest),
            f"{raw_base}/{record_path}": record_bytes,
            f"https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/commits/{COMMIT}": {
                "commit": {"author": {"date": "2026-11-13T00:00:00Z"}}, "author": {"login": "maintainer"}
            },
        }
        opener = FakeOpener(responses)
        client = GitHubResearchClient(opener=opener)
        imported = client.fetch_latest_manifest()
        self.assertEqual(imported.commit_sha, COMMIT)
        self.assertEqual(imported.next_index, FIRST + 2)
        self.assertEqual(imported.record_files[record_path], record_bytes)
        self.assertTrue(all(request.get_header("Authorization") is None for request in opener.requests))
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache" / "global_checkpoint.json"
            client.save_cache(imported, cache)
            cached = client.load_cache(cache)
            self.assertIsNotNone(cached)
            self.assertEqual(cached.source, "cached")
            self.assertEqual(cached.record_files[record_path], record_bytes)

    def test_same_manifest_reuses_only_a_fully_validated_cached_range(self):
        manifest, record_path, record_bytes = manifest_with_range()
        raw_base = f"https://raw.githubusercontent.com/lumina-dev-ace/Riemann-Search-for-App/{COMMIT}"
        api_base = "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App"
        branch_sha = "b" * 40
        responses = {
            api_base: {"default_branch": "main"},
            f"{api_base}/git/ref/heads/main": {"object": {"sha": branch_sha}},
            f"{api_base}/commits?path=data%2Fglobal_manifest.json&sha={branch_sha}&per_page=1": [{"sha": COMMIT}],
            f"{raw_base}/data/global_manifest.json": serialize_document(manifest),
            f"{raw_base}/{record_path}": record_bytes,
            f"{api_base}/commits/{COMMIT}": {
                "commit": {"author": {"date": "2026-11-13T00:00:00Z"}}, "author": {"login": "maintainer"}
            },
        }
        opener = FakeOpener(responses)
        client = GitHubResearchClient(opener=opener)
        imported = client.fetch_latest_manifest()
        first_request_count = len(opener.requests)
        reused = client.fetch_latest_manifest(previous=imported)
        self.assertEqual(reused.source, "live")
        self.assertEqual(reused.record_files[record_path], record_bytes)
        self.assertEqual(len(opener.requests), first_request_count + 3)
        self.assertNotIn(f"{raw_base}/{record_path}", opener.urls[first_request_count:])

        damaged = copy.deepcopy(imported)
        damaged.record_files[record_path] = b"{}"
        refreshed = client.fetch_latest_manifest(previous=damaged)
        self.assertEqual(refreshed.record_files[record_path], record_bytes)
        self.assertIn(f"{raw_base}/{record_path}", opener.urls[first_request_count + 3:])

    def test_public_import_can_select_temporary_migration_branch_without_authentication(self):
        manifest = initial_manifest(FIRST, initialized_at="2026-11-14T00:00:00Z")
        raw_base = f"https://raw.githubusercontent.com/lumina-dev-ace/Riemann-Search-for-App/{COMMIT}"
        branch_ref = "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/git/ref/heads/codex%2Ftemp-migration"
        commits = "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/commits?path=data%2Fglobal_manifest.json&sha=" + "b" * 40 + "&per_page=1"
        responses = {
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App": {"default_branch": "main"},
            branch_ref: {"object": {"sha": "b" * 40}},
            commits: [{"sha": COMMIT}],
            f"{raw_base}/data/global_manifest.json": serialize_document(manifest),
            f"https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/commits/{COMMIT}": {
                "commit": {"author": {"date": "2026-11-14T00:00:00Z"}}, "author": {"login": "maintainer"}
            },
        }
        opener = FakeOpener(responses)
        imported = GitHubResearchClient(opener=opener, branch="codex/temp-migration").fetch_latest_manifest()
        self.assertEqual(imported.branch, "codex/temp-migration")
        self.assertEqual(imported.state["first_required_index"], FIRST)
        self.assertIsNone(imported.state["checkpoint"])
        self.assertEqual(imported.record_files, {})
        self.assertTrue(all(request.get_header("Authorization") is None for request in opener.requests))

    def test_branch_override_rejects_invalid_git_ref_names(self):
        for branch in ("/main", "main/", "main..other", "bad\\ref", "bad ref", "@"):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                GitHubResearchClient(branch=branch)

    def test_missing_manifest_and_network_errors_are_distinguished(self):
        responses = {
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App": {"default_branch": "main"},
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/git/ref/heads/main": {"object": {"sha": "b" * 40}},
            "https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/commits?path=data%2Fglobal_manifest.json&sha=" + "b" * 40 + "&per_page=1": [],
        }
        with self.assertRaises(ManifestMissingError):
            GitHubResearchClient(opener=FakeOpener(responses)).fetch_latest_manifest()
        responses["https://api.github.com/repos/lumina-dev-ace/Riemann-Search-for-App/git/ref/heads/main"] = urllib.error.HTTPError(
            "https://api.github.com/ref", 503, "Service Unavailable", None, None
        )
        with self.assertRaisesRegex(ResearchNetworkError, "HTTP 503") as raised:
            GitHubResearchClient(opener=FakeOpener(responses)).fetch_latest_manifest()
        self.assertNotIsInstance(raised.exception, ManifestMissingError)

    def test_json_parser_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ManifestValidationError, "Duplicate JSON key"):
            parse_json_bytes(b'{"index":"1","index":"2"}')


if __name__ == "__main__":
    unittest.main()
