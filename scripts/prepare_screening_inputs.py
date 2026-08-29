#!/usr/bin/env python3
"""Prepare an ignored title/abstract cache for LLM screening."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml

from collect_pubmed_meta_analyses import EFETCH, ROOT, ISLAND, request, text, write_jsonl


COLLECTION = ISLAND / "collection/2026-08-29"
OUTPUT = ROOT / "generated/vitamin-d-25-oh/screening"
QUERY_ORDER = {
    "q1-measurement": 0,
    "q2-distribution": 1,
    "q3-association": 2,
    "q4-intervention": 3,
    "q5-high-measured-level": 4,
    "q5-supplementation-harm": 5,
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def prepare(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing screening cache: {output}")
    discoveries = read_jsonl(COLLECTION / "discoveries.jsonl")
    by_pmid: dict[str, list[dict]] = {}
    for record in discoveries:
        by_pmid.setdefault(record["identifiers"]["pmid"], []).append(record)

    inputs: dict[str, dict] = {}
    response_log: list[dict] = []
    pmids = sorted(by_pmid, key=int)
    with tempfile.TemporaryDirectory(prefix="helse-screening-", dir=output.parent) as temporary:
        temporary_path = Path(temporary)
        for page, start in enumerate(range(0, len(pmids), 200)):
            batch = pmids[start:start + 200]
            raw, _, retrieved_at = request(EFETCH, {"db": "pubmed", "id": ",".join(batch), "retmode": "xml"})
            response_hash = sha256_bytes(raw)
            response_log.append({
                "page": page,
                "retrieved_at": retrieved_at,
                "requested": len(batch),
                "pmids_sha256": sha256_bytes("\n".join(batch).encode("utf-8")),
                "response_sha256": response_hash,
            })
            for article in ET.fromstring(raw).findall("PubmedArticle"):
                citation = article.find("MedlineCitation")
                article_node = citation.find("Article") if citation is not None else None
                pmid = text(citation.find("PMID")) if citation is not None else None
                if not pmid or article_node is None:
                    raise ValueError("PubMed screening source lacks PMID or Article")
                occurrences = sorted(by_pmid[pmid], key=lambda item: QUERY_ORDER[item["query_ids"][0]])
                sections = []
                for index, section in enumerate(article_node.findall(".//Abstract/AbstractText")):
                    value = text(section)
                    if value:
                        sections.append({
                            "location_id": f"abstract:{index}",
                            "label": section.attrib.get("Label"),
                            "text": value,
                            "sha256": sha256_bytes(value.encode("utf-8")),
                        })
                title = text(article_node.find("ArticleTitle")) or occurrences[0]["title"]
                inputs[pmid] = {
                    "record_id": occurrences[0]["id"],
                    "pmid": pmid,
                    "source_url": occurrences[0]["source_url"],
                    "query_ids": [item["query_ids"][0] for item in occurrences],
                    "source_record_ids": [item["id"] for item in occurrences],
                    "publication_types": {
                        "location_id": "publication_types",
                        "values": occurrences[0]["provenance"].get("publication_types", []),
                        "sha256": sha256_bytes(canonical_json(occurrences[0]["provenance"].get("publication_types", []))),
                    },
                    "title": {"location_id": "title", "text": title, "sha256": sha256_bytes(title.encode("utf-8"))},
                    "abstract_sections": sections,
                    "source_response_sha256": response_hash,
                }
        if set(inputs) != set(pmids):
            raise ValueError("screening input PMID mismatch")
        ordered_inputs = [inputs[pmid] for pmid in pmids]
        write_jsonl(temporary_path / "inputs.jsonl", ordered_inputs)
        manifest = {
            "screening_input": {
                "source_collection_manifest_sha256": sha256_bytes((COLLECTION / "manifest.yaml").read_bytes()),
                "record_count": len(ordered_inputs),
                "input_sha256": sha256_bytes((temporary_path / "inputs.jsonl").read_bytes()),
                "pubmed_responses": response_log,
                "copyright": "Ephemeral title/abstract processing cache; do not commit.",
            }
        }
        (temporary_path / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_path), str(output))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        prepare(arguments.output.resolve())
    except (FileExistsError, KeyError, OSError, ValueError, ET.ParseError, yaml.YAMLError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Prepared screening inputs at {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
