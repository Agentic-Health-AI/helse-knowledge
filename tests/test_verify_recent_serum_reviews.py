from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_recent_serum_reviews as verifier
import collect_recent_serum_reviews as collector


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def refresh_manifest(path: Path, collection: str) -> None:
    manifest_path = path / "manifest.yaml"
    document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    spec = document["collection"]["records"][collection]
    artifact = path / spec["path"]
    spec["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    spec["count"] = len(artifact.read_text(encoding="utf-8").splitlines())
    manifest_path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


class RecentSerumReviewVerifierTests(unittest.TestCase):
    def copy_collection(self, temporary: str) -> Path:
        path = Path(temporary) / "collection"
        shutil.copytree(verifier.COLLECTION, path)
        return path

    def test_committed_collection_passes(self):
        self.assertEqual([], verifier.verify())

    def test_committed_abstract_text_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_collection(temporary)
            discoveries_path = path / "discoveries.jsonl"
            records = verifier.read_jsonl(discoveries_path)
            records[0]["abstract"] = "Unlicensed text must not be committed."
            write_jsonl(discoveries_path, records)
            refresh_manifest(path, "discoveries")
            self.assertIn("recent-review committed abstract text", verifier.verify(path))

    def test_broken_abstract_identity_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_collection(temporary)
            discoveries_path = path / "discoveries.jsonl"
            records = verifier.read_jsonl(discoveries_path)
            records[0]["abstract_sha256"] = "invalid"
            write_jsonl(discoveries_path, records)
            refresh_manifest(path, "discoveries")
            self.assertIn("recent-review abstract identity", verifier.verify(path))

    def test_raw_search_response_tampering_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_collection(temporary)
            requests_path = path / "requests.jsonl"
            records = verifier.read_jsonl(requests_path)
            records[0]["response_body"] += " "
            write_jsonl(requests_path, records)
            refresh_manifest(path, "requests")
            self.assertIn("recent-review ESearch response hash", verifier.verify(path))

    def test_missing_discovery_is_rejected_after_rehash(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_collection(temporary)
            discoveries_path = path / "discoveries.jsonl"
            write_jsonl(discoveries_path, verifier.read_jsonl(discoveries_path)[1:])
            refresh_manifest(path, "discoveries")
            self.assertIn("recent-review discovery coverage", verifier.verify(path))

    def test_undeclared_jsonl_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.copy_collection(temporary)
            (path / "extra.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertIn("undeclared recent-review JSONL", verifier.verify(path))

    def test_unsafe_repository_cache_path_is_rejected(self):
        unsafe = verifier.ROOT / "abstracts.jsonl"
        self.assertIn("recent-review unsafe abstract cache path", verifier.verify(cache=unsafe))
        with self.assertRaisesRegex(ValueError, "must be under generated"):
            collector.ensure_rights_safe_cache(unsafe)

    def test_refetch_derives_abstract_and_metadata(self):
        abstract = "Synthetic abstract for mechanical verification."
        xml = f"""<?xml version="1.0"?>
<PubmedArticleSet><PubmedArticle><MedlineCitation>
<PMID>1</PMID><DateRevised><Year>2026</Year><Month>08</Month><Day>30</Day></DateRevised>
<Article><Journal><JournalIssue><PubDate><Year>2026</Year><Month>Aug</Month></PubDate></JournalIssue><Title>Test Journal</Title></Journal>
<ArticleTitle>Synthetic review</ArticleTitle><ArticleDate><Year>2026</Year><Month>08</Month><Day>29</Day></ArticleDate>
<Abstract><AbstractText>{abstract}</AbstractText></Abstract>
<AuthorList><Author><ForeName>Ada</ForeName><LastName>Test</LastName></Author></AuthorList>
<PublicationTypeList><PublicationType>Systematic Review</PublicationType></PublicationTypeList>
</Article></MedlineCitation><PubmedData><ArticleIdList><ArticleId IdType="doi">10.1/test</ArticleId></ArticleIdList></PubmedData>
</PubmedArticle></PubmedArticleSet>""".encode()
        response_hash = hashlib.sha256(xml).hexdigest()
        requests = [{
            "request_type": "efetch",
            "request_url": "https://example.invalid/efetch",
            "requested_pmids": ["1"],
            "response_sha256": response_hash,
        }]
        discoveries = [{
            "identifiers": {"pmid": "1", "doi": "10.1/test"},
            "title": "Synthetic review",
            "authors": ["Ada Test"],
            "venue": "Test Journal",
            "publication_date": "2026-08",
            "electronic_publication_date": "2026-08-29",
            "pubmed_revision_date": "2026-08-30",
            "version_status": "final-publication",
            "abstract_sha256": hashlib.sha256(abstract.encode()).hexdigest(),
            "abstract_character_count": len(abstract),
            "provenance": {"publication_types": ["Systematic Review"]},
        }]
        with patch.object(verifier, "fetch_url", return_value=xml):
            self.assertEqual([], verifier.verify_refetched_sources(requests, discoveries))
            discoveries[0]["abstract_sha256"] = "0" * 64
            self.assertIn(
                "recent-review PubMed source-derived record",
                verifier.verify_refetched_sources(requests, discoveries),
            )


if __name__ == "__main__":
    unittest.main()
