from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_discovery_collection as verifier


class DiscoveryCollectionVerifierTests(unittest.TestCase):
    def test_committed_collection_passes(self):
        self.assertEqual([], verifier.verify())

    def test_modified_discovery_file_fails_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary) / "collection"
            shutil.copytree(verifier.COLLECTION, collection)
            discovery_path = collection / "discoveries.jsonl"
            discovery_path.write_text(discovery_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assertIn("collection file hash: discoveries", verifier.verify(collection))

    def test_broken_query_trace_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            collection = Path(temporary) / "collection"
            shutil.copytree(verifier.COLLECTION, collection)
            discovery_path = collection / "discoveries.jsonl"
            lines = discovery_path.read_text(encoding="utf-8").splitlines()
            record = json.loads(lines[0])
            record["query_ids"] = ["q2-distribution"]
            lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            discovery_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            errors = verifier.verify(collection)
            self.assertIn("collection file hash: discoveries", errors)
            self.assertIn("discovery query trace", errors)


if __name__ == "__main__":
    unittest.main()
