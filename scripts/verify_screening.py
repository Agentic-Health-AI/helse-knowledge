#!/usr/bin/env python3
"""Verify source-bound LLM screening and deterministic reduction artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import yaml

from finalize_screening import reduce_decision
from verify_repository import validate_schema


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
SOURCE_COLLECTION = ISLAND / "collection/2026-08-29"
SCREENING = ISLAND / "screening/2026-08-29"
PROMPT = ROOT / "prompts/screening-0.1.yaml"
SCHEMAS = {
    "discoveries": ROOT / "schemas/discovery.schema.yaml",
    "screenings": ROOT / "schemas/screening.schema.yaml",
    "relations": ROOT / "schemas/relation-study-identity.schema.yaml",
    "verification_events": ROOT / "schemas/verification-event.schema.yaml",
}
REQUIRED_LLM_PROVENANCE = {"model_id", "model_revision", "prompt_id", "input_sha256", "output_sha256", "source_locations"}


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


def verify(screening_path: Path = SCREENING) -> list[str]:
    errors: list[str] = []
    try:
        manifest = yaml.safe_load((screening_path / "manifest.yaml").read_text(encoding="utf-8"))["screening"]
        source_manifest = yaml.safe_load((SOURCE_COLLECTION / "manifest.yaml").read_text(encoding="utf-8"))["collection"]
        prompt_document = yaml.safe_load(PROMPT.read_text(encoding="utf-8"))
        if manifest.get("source_collection_manifest_sha256") != sha256(SOURCE_COLLECTION / "manifest.yaml"):
            errors.append("screening source collection hash")
        if manifest.get("prompt_sha256") != sha256(PROMPT):
            errors.append("screening prompt hash")
        if manifest.get("parser_prompt_id") != prompt_document["parser"]["id"] or manifest.get("auditor_prompt_id") != prompt_document["auditor"]["id"]:
            errors.append("screening prompt identity")

        collections: dict[str, list[dict[str, Any]]] = {}
        declared_paths = set()
        for name, schema_path in SCHEMAS.items():
            spec = manifest["records"][name]
            path = (screening_path / spec["path"]).resolve()
            if path.parent != screening_path.resolve():
                errors.append("screening path escapes run directory")
                continue
            declared_paths.add(path)
            if sha256(path) != spec["sha256"]:
                errors.append(f"screening file hash: {name}")
            records = read_jsonl(path)
            collections[name] = records
            if len(records) != spec["count"]:
                errors.append(f"screening file count: {name}")
            schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
            for index, record in enumerate(records):
                errors.extend(validate_schema(record, schema, f"{name}[{index}]"))
        if declared_paths != {path.resolve() for path in screening_path.glob("*.jsonl")}:
            errors.append("undeclared screening JSONL")

        discoveries = {record["id"]: record for record in collections.get("discoveries", [])}
        screenings = {record["id"]: record for record in collections.get("screenings", [])}
        events = {record["id"]: record for record in collections.get("verification_events", [])}
        source_records = read_jsonl(SOURCE_COLLECTION / "discoveries.jsonl")
        source_by_id = {record["id"]: record for record in source_records}
        source_pmids = {record["identifiers"]["pmid"] for record in source_records}
        if len(discoveries) != source_manifest.get("unique_pmids") or {record["identifiers"]["pmid"] for record in discoveries.values()} != source_pmids:
            errors.append("screening PMID coverage")
        if len(screenings) != len(discoveries) or manifest.get("record_count") != len(screenings):
            errors.append("screening record coverage")

        decision_counts = Counter()
        for screening in screenings.values():
            decision_counts[screening.get("decision")] += 1
            discovery = discoveries.get(screening.get("record_id"))
            if discovery is None or discovery.get("state") != screening.get("decision"):
                errors.append("screening discovery state")
                continue
            event_ids = screening.get("evaluation_events", [])
            linked = [events.get(event_id) for event_id in event_ids]
            if len(linked) != 3 or any(event is None for event in linked):
                errors.append("screening event chain")
                continue
            parser_event, auditor_event, reducer_event = linked
            if [parser_event.get("action"), auditor_event.get("action"), reducer_event.get("action")] != ["parse", "audit", "reduce"]:
                errors.append("screening event order")
                continue
            if parser_event.get("actor_type") != "llm" or auditor_event.get("actor_type") != "llm" or reducer_event.get("actor_type") != "validator":
                errors.append("screening actor chain")
            for event in (parser_event, auditor_event):
                provenance = event.get("provenance", {})
                if not REQUIRED_LLM_PROVENANCE <= set(provenance):
                    errors.append("screening LLM provenance")
                locations = provenance.get("source_locations", [])
                hashes = provenance.get("source_content_sha256", {})
                if set(locations) != set(hashes):
                    errors.append("screening source-bound provenance")
                assessments = provenance.get("assessments", {})
                if any(value.get("outcome") == "supported" for value in assessments.values()) and not locations:
                    errors.append("supported screening fact lacks source location")
                if any(key in provenance for key in ("abstract", "abstract_sections", "full_text")):
                    errors.append("screening republishes source text")
            facts = parser_event.get("provenance", {}).get("facts", {})
            assessments = auditor_event.get("provenance", {}).get("assessments", {})
            expected_decision, expected_reason, audited = reduce_decision(facts, assessments)
            if screening.get("decision") != expected_decision or screening.get("exclusion_reason") != expected_reason:
                errors.append("screening reducer decision")
            if reducer_event.get("outcome") != expected_decision or reducer_event.get("provenance", {}).get("audited_facts") != audited:
                errors.append("screening reducer provenance")
            if any(event.get("target_id") != screening.get("id") for event in linked):
                errors.append("screening event target")

        if dict(sorted(decision_counts.items())) != manifest.get("decision_counts"):
            errors.append("screening decision counts")

        relations = collections.get("relations", [])
        if len(relations) != len(source_records) - len(source_pmids) or len(relations) != manifest.get("duplicate_relations"):
            errors.append("screening duplicate relation count")
        for relation in relations:
            source = source_by_id.get(relation.get("from_id"))
            target = source_by_id.get(relation.get("to_id"))
            if source is None or target is None or relation.get("relation_type") != "duplicate-of" or relation.get("match_basis") != "exact-pmid":
                errors.append("screening duplicate relation")
                continue
            if source["identifiers"]["pmid"] != target["identifiers"]["pmid"] or relation.get("to_id") not in discoveries:
                errors.append("screening duplicate PMID")
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as error:
        errors.append(f"load error: {error}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening", type=Path, default=SCREENING)
    arguments = parser.parse_args()
    errors = verify(arguments.screening.resolve())
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("LLM screening verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
