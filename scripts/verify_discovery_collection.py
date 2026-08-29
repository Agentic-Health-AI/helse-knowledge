#!/usr/bin/env python3
"""Verify the frozen PubMed discovery-only collection."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

from verify_repository import validate_schema


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
COLLECTION = ISLAND / "collection/2026-08-29"
PROTOCOL_PATH = ISLAND / "protocol.yaml"
AMENDMENT_PATH = ISLAND / "amendments/0.1.1-meta-analysis-pilot.yaml"
SEARCH_SCHEMA = ROOT / "schemas/search-run.schema.yaml"
DISCOVERY_SCHEMA = ROOT / "schemas/discovery.schema.yaml"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: record must be an object")
        records.append(value)
    return records


def verify(collection_path: Path = COLLECTION) -> list[str]:
    errors: list[str] = []
    try:
        document = yaml.safe_load((collection_path / "manifest.yaml").read_text(encoding="utf-8"))
        manifest = document["collection"]
        amendment_document = yaml.safe_load(AMENDMENT_PATH.read_text(encoding="utf-8"))
        amendment = amendment_document["amendment"]
        queries = amendment_document["pubmed"]["query_families"]
        search_schema = yaml.safe_load(SEARCH_SCHEMA.read_text(encoding="utf-8"))
        discovery_schema = yaml.safe_load(DISCOVERY_SCHEMA.read_text(encoding="utf-8"))

        if manifest.get("mode") != "discovery-only" or manifest.get("source") != "pubmed":
            errors.append("collection mode/source")
        if manifest.get("base_protocol_sha256") != sha256(PROTOCOL_PATH):
            errors.append("collection base protocol hash")
        if manifest.get("amendment_id") != amendment.get("amendment_id") or manifest.get("amendment_sha256") != sha256(AMENDMENT_PATH):
            errors.append("collection amendment provenance")

        declared_paths: set[Path] = set()
        collections: dict[str, list[dict[str, Any]]] = {}
        for name in ("searches", "discoveries"):
            spec = manifest["records"][name]
            path = (collection_path / spec["path"]).resolve()
            if path.parent != collection_path.resolve():
                errors.append("collection path escapes run directory")
                continue
            declared_paths.add(path)
            if sha256(path) != spec["sha256"]:
                errors.append(f"collection file hash: {name}")
            collections[name] = read_jsonl(path)
            if len(collections[name]) != spec["count"]:
                errors.append(f"collection file count: {name}")
        if declared_paths != {path.resolve() for path in collection_path.glob("*.jsonl")}:
            errors.append("undeclared collection JSONL")

        searches = collections.get("searches", [])
        discoveries = collections.get("discoveries", [])
        for index, record in enumerate(searches):
            errors.extend(validate_schema(record, search_schema, f"searches[{index}]"))
        for index, record in enumerate(discoveries):
            errors.extend(validate_schema(record, discovery_schema, f"discoveries[{index}]"))

        if {record.get("query_id") for record in searches} != set(queries):
            errors.append("collection query set")
        search_by_id = {record.get("id"): record for record in searches}
        if len(search_by_id) != len(searches):
            errors.append("duplicate search run id")
        discovery_ids = [record.get("id") for record in discoveries]
        if len(discovery_ids) != len(set(discovery_ids)):
            errors.append("duplicate discovery id")

        result_counts = {record["query_id"]: 0 for record in searches}
        pmids: set[str] = set()
        for record in discoveries:
            search = search_by_id.get(record.get("search_run_id"))
            query_ids = record.get("query_ids", [])
            pmid = record.get("identifiers", {}).get("pmid")
            if search is None or query_ids != [search.get("query_id")]:
                errors.append("discovery query trace")
                continue
            if record.get("source") != "pubmed" or record.get("source_url") != f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/":
                errors.append("discovery PubMed source")
            if record.get("state") != "discovered" or not pmid:
                errors.append("discovery state/PMID")
            result_counts[search["query_id"]] += 1
            pmids.add(pmid)
        for search in searches:
            if search.get("run_status") != "executed" or search.get("protocol_id") != amendment.get("amendment_id"):
                errors.append("search execution provenance")
            if search.get("query_or_endpoint") != queries.get(search.get("query_id")):
                errors.append("search literal query mismatch")
            if result_counts.get(search.get("query_id")) != search.get("result_count"):
                errors.append("search result count mismatch")
            if not search.get("pagination_log"):
                errors.append("search pagination log")
        if manifest.get("query_result_records") != len(discoveries) or manifest.get("unique_pmids") != len(pmids):
            errors.append("collection summary counts")
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as error:
        errors.append(f"load error: {error}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=COLLECTION)
    arguments = parser.parse_args()
    errors = verify(arguments.collection.resolve())
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PubMed discovery collection verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
