#!/usr/bin/env python3
"""Reduce validated LLM screening runs into canonical screening artifacts."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
SOURCE_COLLECTION = ISLAND / "collection/2026-08-29"
INPUT_PATH = ROOT / "generated/vitamin-d-25-oh/screening/inputs.jsonl"
RUNS_PATH = ROOT / "generated/vitamin-d-25-oh/screening/runs-schema-20"
PROMPT_PATH = ROOT / "prompts/screening-0.1.yaml"
OUTPUT_PATH = ISLAND / "screening/2026-08-29"
FACT_ORDER = [
    "meta_analysis",
    "human_research",
    "adults_in_scope",
    "serum_or_plasma_25_oh_d",
    "eligible_question",
    "eligible_underlying_design",
    "eligible_outcome",
    "sufficient_for_screening",
]
EXCLUSION_RULES = [
    ("meta_analysis", "wrong-design"),
    ("human_research", "non-human"),
    ("adults_in_scope", "wrong-population"),
    ("serum_or_plasma_25_oh_d", "wrong-analyte-or-specimen"),
    ("eligible_question", "wrong-question"),
    ("eligible_underlying_design", "wrong-design"),
    ("eligible_outcome", "wrong-outcome"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical_json(record).decode("utf-8"))
            handle.write("\n")


def reduce_decision(facts: dict[str, Any], assessments: dict[str, Any]) -> tuple[str, str | None, dict[str, bool | None]]:
    audited = {
        name: facts[name]["value"] if assessments[name]["outcome"] == "supported" else None
        for name in FACT_ORDER
    }
    for fact_name, reason in EXCLUSION_RULES:
        if audited[fact_name] is False:
            return "excluded", reason, audited
    if all(audited[name] is True for name in FACT_ORDER):
        return "included", None, audited
    return "awaiting-full-text", None, audited


def load_runs(runs_path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    parser_records: dict[str, dict[str, Any]] = {}
    auditor_records: dict[str, dict[str, Any]] = {}
    run_by_record: dict[str, dict[str, Any]] = {}
    for result_path in sorted(runs_path.glob("batch-*/result.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        parser_items = result["parser"]["payload"]["records"]
        auditor_items = result["auditor"]["payload"]["records"]
        if [item["record_id"] for item in parser_items] != [item["record_id"] for item in auditor_items]:
            raise ValueError(f"parser/auditor record mismatch: {result_path}")
        for parser_item, auditor_item in zip(parser_items, auditor_items):
            record_id = parser_item["record_id"]
            if record_id in parser_records:
                raise ValueError(f"duplicate LLM screening record: {record_id}")
            parser_records[record_id] = parser_item
            auditor_records[record_id] = auditor_item
            run_by_record[record_id] = result
    return parser_records, auditor_records, run_by_record


def finalize(input_path: Path, runs_path: Path, output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite screening output: {output_path}")
    inputs = read_jsonl(input_path)
    source_discoveries = read_jsonl(SOURCE_COLLECTION / "discoveries.jsonl")
    source_by_id = {record["id"]: record for record in source_discoveries}
    parser_records, auditor_records, run_by_record = load_runs(runs_path)
    input_ids = {record["record_id"] for record in inputs}
    if set(parser_records) != input_ids or set(auditor_records) != input_ids:
        raise ValueError(f"incomplete screening coverage: inputs={len(input_ids)}, parser={len(parser_records)}, auditor={len(auditor_records)}")

    prompt_sha = sha256_path(PROMPT_PATH)
    prompt_document = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    runner_version = subprocess.run(["codex", "--version"], text=True, stdout=subprocess.PIPE, check=True).stdout.strip()
    discoveries: list[dict[str, Any]] = []
    screenings: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for source in inputs:
        record_id = source["record_id"]
        pmid = source["pmid"]
        parser_item = parser_records[record_id]
        auditor_item = auditor_records[record_id]
        run = run_by_record[record_id]
        decision, exclusion_reason, audited = reduce_decision(parser_item["facts"], auditor_item["assessments"])
        state = decision
        screening_id = f"https://github.com/Agentic-Health-AI/helse-knowledge/screening/pubmed/{pmid}"
        parser_event_id = f"{screening_id}/events/parser"
        auditor_event_id = f"{screening_id}/events/auditor"
        reducer_event_id = f"{screening_id}/events/reducer"
        source_hashes = {
            source["publication_types"]["location_id"]: source["publication_types"]["sha256"],
            source["title"]["location_id"]: source["title"]["sha256"],
        }
        source_hashes.update({section["location_id"]: section["sha256"] for section in source["abstract_sections"]})

        canonical_discovery = dict(source_by_id[record_id])
        canonical_discovery["state"] = state
        canonical_discovery["provenance"] = {
            **canonical_discovery["provenance"],
            "matched_query_ids": source["query_ids"],
            "query_result_record_ids": source["source_record_ids"],
        }
        discoveries.append(canonical_discovery)
        screenings.append({
            "id": screening_id,
            "record_type": "screening",
            "record_id": record_id,
            "decision": decision,
            "decision_status": "llm-audited",
            "exclusion_reason": exclusion_reason,
            "evaluation_events": [parser_event_id, auditor_event_id, reducer_event_id],
            "state_history": ["discovered", "screening", state],
        })

        for duplicate_id in source["source_record_ids"][1:]:
            relations.append({
                "id": f"https://github.com/Agentic-Health-AI/helse-knowledge/relations/exact-pmid/{pmid}/{len(relations)}",
                "record_type": "relation-study-identity",
                "relation_type": "duplicate-of",
                "from_id": duplicate_id,
                "to_id": record_id,
                "match_basis": "exact-pmid",
                "status": "exact-match",
                "auto_merged": True,
            })

        parser_locations = sorted({location for fact in parser_item["facts"].values() for location in fact["locations"]})
        auditor_locations = sorted({location for assessment in auditor_item["assessments"].values() for location in assessment["locations"]})
        common_parser = run["parser"]
        common_auditor = run["auditor"]
        events.extend([
            {
                "id": parser_event_id,
                "record_type": "verification-event",
                "actor_type": "llm",
                "action": "parse",
                "target_id": screening_id,
                "outcome": "candidate-facts",
                "timestamp": common_parser["finished_at"],
                "provenance": {
                    "model_id": common_parser["model"],
                    "model_revision": common_parser["model"],
                    "prompt_id": common_parser["prompt_id"],
                    "prompt_sha256": prompt_sha,
                    "input_sha256": common_parser["input_sha256"],
                    "output_sha256": common_parser["output_sha256"],
                    "source_locations": parser_locations,
                    "source_content_sha256": {key: source_hashes[key] for key in parser_locations},
                    "facts": parser_item["facts"],
                    "runner": runner_version,
                    "usage": common_parser.get("usage"),
                },
            },
            {
                "id": auditor_event_id,
                "record_type": "verification-event",
                "actor_type": "llm",
                "action": "audit",
                "target_id": screening_id,
                "outcome": "audited-facts",
                "timestamp": common_auditor["finished_at"],
                "provenance": {
                    "model_id": common_auditor["model"],
                    "model_revision": common_auditor["model"],
                    "prompt_id": common_auditor["prompt_id"],
                    "prompt_sha256": prompt_sha,
                    "input_sha256": common_auditor["input_sha256"],
                    "output_sha256": common_auditor["output_sha256"],
                    "source_locations": auditor_locations,
                    "source_content_sha256": {key: source_hashes[key] for key in auditor_locations},
                    "assessments": auditor_item["assessments"],
                    "runner": runner_version,
                    "usage": common_auditor.get("usage"),
                },
            },
            {
                "id": reducer_event_id,
                "record_type": "verification-event",
                "actor_type": "validator",
                "action": "reduce",
                "target_id": screening_id,
                "outcome": decision,
                "timestamp": utc_now(),
                "provenance": {
                    "rule_version": "screening-reducer/0.1",
                    "input_event_ids": [parser_event_id, auditor_event_id],
                    "audited_facts": audited,
                },
            },
        ])

    decision_counts = Counter(record["decision"] for record in screenings)
    with tempfile.TemporaryDirectory(prefix="helse-screening-output-", dir=output_path.parent) as temporary:
        temporary_path = Path(temporary)
        paths = {
            "discoveries": temporary_path / "discoveries.jsonl",
            "screenings": temporary_path / "screenings.jsonl",
            "relations": temporary_path / "relations.jsonl",
            "verification_events": temporary_path / "verification-events.jsonl",
        }
        for name, records in (("discoveries", discoveries), ("screenings", screenings), ("relations", relations), ("verification_events", events)):
            write_jsonl(paths[name], records)
        manifest = {
            "screening": {
                "id": "https://github.com/Agentic-Health-AI/helse-knowledge/screening-runs/2026-08-29",
                "source_collection_manifest_sha256": sha256_path(SOURCE_COLLECTION / "manifest.yaml"),
                "prompt_path": "../../../../prompts/screening-0.1.yaml",
                "prompt_sha256": prompt_sha,
                "parser_prompt_id": prompt_document["parser"]["id"],
                "auditor_prompt_id": prompt_document["auditor"]["id"],
                "reducer": "screening-reducer/0.1",
                "record_count": len(screenings),
                "decision_counts": dict(sorted(decision_counts.items())),
                "duplicate_relations": len(relations),
                "records": {
                    name: {"path": path.name, "sha256": sha256_path(path), "count": sum(1 for _ in path.open(encoding="utf-8"))}
                    for name, path in paths.items()
                },
            }
        }
        (temporary_path / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_path), str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--runs", type=Path, default=RUNS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        finalize(arguments.input.resolve(), arguments.runs.resolve(), arguments.output.resolve())
    except (FileExistsError, KeyError, OSError, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Finalized screening artifacts at {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
