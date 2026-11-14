from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import validate_research_repository as validator


class RepositoryManifestTests(unittest.TestCase):
    def setUp(self):
        self.initial = json.loads((ROOT / "data" / "global_manifest.json").read_text(encoding="utf-8"))

    @staticmethod
    def seal(document):
        value = copy.deepcopy(document)
        value.pop("integrity", None)
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        value["integrity"] = {"algorithm": "sha256", "sha256": hashlib.sha256(canonical).hexdigest()}
        return value

    def test_approved_initial_manifest_has_no_fabricated_progress(self):
        self.assertEqual(self.initial["status"], "initialized")
        self.assertEqual(self.initial["first_required_index"], "10000000000000")
        self.assertIsNone(self.initial["global_checkpoint_index"])
        self.assertEqual(self.initial["accepted_ranges"], [])
        validator.validate()

    def test_uninitialized_manifest_never_claims_zero_or_progress(self):
        manifest = self.seal({
            "schema_version": 1, "network_id": "riemannsearch-global-research", "status": "uninitialized",
            "initialized_at": None, "first_required_index": None, "global_checkpoint_index": None,
            "accepted_ranges": [], "publication_history": [], "last_updated_at": None,
        })
        self.assertEqual(manifest["global_checkpoint_index"], None)

    def test_integrity_tampering_is_rejected(self):
        original = json.loads(json.dumps(self.initial))
        original["first_required_index"] = "1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data" / "ranges").mkdir(parents=True)
            (root / "data" / "global_manifest.json").write_text(json.dumps(original), encoding="utf-8")
            old_root = validator.ROOT
            try:
                validator.ROOT = root
                with self.assertRaisesRegex(ValueError, "integrity mismatch"):
                    validator.validate()
            finally:
                validator.ROOT = old_root

    def test_website_uses_manifest_and_uninitialized_copy(self):
        script = (ROOT / "progress" / "app.js").read_text(encoding="utf-8")
        self.assertIn("commits?path=data%2Fglobal_manifest.json&sha=main", script)
        self.assertIn("raw.githubusercontent.com/${REPOSITORY}/${commit}", script)
        self.assertIn("Research network awaiting initialization.", script)
        self.assertIn("cache: \"no-store\"", script)
        self.assertIn("parseJsonNoDuplicateKeys", script)
        self.assertIn("validateRecordFile", script)
        self.assertIn("setInterval(() => { if (!document.hidden) render(); }, 5 * 60 * 1000)", script)
        self.assertNotIn("innerHTML", script)


if __name__ == "__main__":
    unittest.main()
