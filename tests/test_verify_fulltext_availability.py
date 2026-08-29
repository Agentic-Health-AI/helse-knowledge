from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_fulltext_availability as verifier


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def refresh_manifest(path: Path, collection: str) -> None:
    manifest_path = path / "manifest.yaml"
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    spec = document["fulltext_availability"][collection]
    artifact = path / spec["path"]
    spec["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    spec["count"] = len(artifact.read_text(encoding="utf-8").splitlines())
    manifest_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


class FulltextAvailabilityVerifierTests(unittest.TestCase):
    def copy_inventory(self, temporary: str) -> Path:
        path = Path(temporary) / "fulltext"
        shutil.copytree(verifier.FULLTEXT, path)
        return path

    def test_committed_inventory_passes(self):
        self.assertEqual([], verifier.verify())

    def test_screening_manifest_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            manifest_path = path / "manifest.yaml"
            document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            document["fulltext_availability"]["source_screening_manifest_sha256"] = "0" * 64
            manifest_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
            self.assertIn("full-text source screening hash", verifier.verify(path))

    def test_source_mismatch_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            records_path = path / "availability.jsonl"
            records = verifier.read_jsonl(records_path)
            records[0]["pmid"] = "99999999"
            write_jsonl(records_path, records)
            refresh_manifest(path, "records")
            self.assertIn("full-text source-derived record", verifier.verify(path))

    def test_fail_closed_rule_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            records_path = path / "availability.jsonl"
            records = verifier.read_jsonl(records_path)
            record = next(item for item in records if item["access_status"] != "pmc-open-access")
            record["extraction_allowed"] = True
            write_jsonl(records_path, records)
            refresh_manifest(path, "records")
            self.assertIn("full-text source-derived record", verifier.verify(path))

    def test_raw_response_tampering_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            requests_path = path / "requests.jsonl"
            requests = verifier.read_jsonl(requests_path)
            requests[0]["response_body"] += " "
            write_jsonl(requests_path, requests)
            refresh_manifest(path, "requests")
            self.assertIn("full-text response hash", verifier.verify(path))

    def test_missing_record_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            records_path = path / "availability.jsonl"
            records = verifier.read_jsonl(records_path)[1:]
            write_jsonl(records_path, records)
            refresh_manifest(path, "records")
            self.assertIn("full-text screening coverage", verifier.verify(path))

    def test_undeclared_jsonl_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_inventory(temporary)
            (path / "extra.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertIn("undeclared full-text JSONL", verifier.verify(path))


if __name__ == "__main__":
    unittest.main()
