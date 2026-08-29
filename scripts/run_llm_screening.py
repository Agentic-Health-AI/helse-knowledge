#!/usr/bin/env python3
"""Run source-bound parser and auditor calls over screening batches."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = ROOT / "generated/vitamin-d-25-oh/screening/inputs.jsonl"
OUTPUT_PATH = ROOT / "generated/vitamin-d-25-oh/screening/runs-schema-20"
PROMPT_PATH = ROOT / "prompts/screening-0.1.yaml"
MODEL = "gpt-5.6-luna"
FACTS = {
    "meta_analysis",
    "human_research",
    "adults_in_scope",
    "serum_or_plasma_25_oh_d",
    "eligible_question",
    "eligible_underlying_design",
    "eligible_outcome",
    "sufficient_for_screening",
}
AUDIT_OUTCOMES = {"supported", "unsupported", "conflict", "unknown"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def locations(record: dict[str, Any]) -> set[str]:
    return {
        record["publication_types"]["location_id"],
        record["title"]["location_id"],
        *(section["location_id"] for section in record["abstract_sections"]),
    }


def normalize_record_order(payload: dict[str, Any], source_records: list[dict[str, Any]], label: str) -> None:
    records = payload.get("records")
    expected_ids = [item["record_id"] for item in source_records]
    if isinstance(records, dict):
        if set(records) != set(expected_ids):
            raise ValueError(f"{label} record set")
        payload["records"] = [{"record_id": record_id, **records[record_id]} for record_id in expected_ids]
        return
    actual_ids = [item.get("record_id") for item in records] if isinstance(records, list) else []
    if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) != set(expected_ids):
        raise ValueError(f"{label} record set")
    order = {record_id: index for index, record_id in enumerate(expected_ids)}
    records.sort(key=lambda item: order[item["record_id"]])


def validate_parser(payload: dict[str, Any], source_records: list[dict[str, Any]]) -> None:
    normalize_record_order(payload, source_records, "parser")
    records = payload.get("records")
    source_by_id = {item["record_id"]: item for item in source_records}
    for record in records:
        if set(record.get("facts", {})) != FACTS:
            raise ValueError(f"parser fact set: {record.get('record_id')}")
        allowed_locations = locations(source_by_id[record["record_id"]])
        for fact in record["facts"].values():
            if fact.get("value") not in (True, False, None):
                raise ValueError("parser fact value")
            if not isinstance(fact.get("locations"), list) or not set(fact["locations"]) <= allowed_locations:
                raise ValueError("parser source location")


def validate_auditor(payload: dict[str, Any], source_records: list[dict[str, Any]]) -> None:
    normalize_record_order(payload, source_records, "auditor")
    records = payload.get("records")
    source_by_id = {item["record_id"]: item for item in source_records}
    for record in records:
        if set(record.get("assessments", {})) != FACTS:
            raise ValueError(f"auditor fact set: {record.get('record_id')}")
        allowed_locations = locations(source_by_id[record["record_id"]])
        for assessment in record["assessments"].values():
            if assessment.get("outcome") not in AUDIT_OUTCOMES:
                raise ValueError("auditor outcome")
            if not isinstance(assessment.get("locations"), list) or not set(assessment["locations"]) <= allowed_locations:
                raise ValueError("auditor source location")


def output_schema(source_records: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    record_ids = [record["record_id"] for record in source_records]
    record_properties = {}
    for record in source_records:
        location_schema = {"type": "array", "items": {"type": "string", "enum": sorted(locations(record))}}
        if phase == "parser":
            value = {
                "type": "object",
                "properties": {"value": {"type": ["boolean", "null"]}, "locations": location_schema},
                "required": ["value", "locations"],
                "additionalProperties": False,
            }
            field_name = "facts"
        else:
            value = {
                "type": "object",
                "properties": {"outcome": {"type": "string", "enum": sorted(AUDIT_OUTCOMES)}, "locations": location_schema},
                "required": ["outcome", "locations"],
                "additionalProperties": False,
            }
            field_name = "assessments"
        fields = {name: value for name in sorted(FACTS)}
        record_properties[record["record_id"]] = {
            "type": "object",
            "properties": {
                field_name: {"type": "object", "properties": fields, "required": sorted(FACTS), "additionalProperties": False},
                "notes": {"type": "string"},
            },
            "required": [field_name, "notes"],
            "additionalProperties": False,
        }
    return {
        "type": "object",
        "properties": {"records": {"type": "object", "properties": record_properties, "required": record_ids, "additionalProperties": False}},
        "required": ["records"],
        "additionalProperties": False,
    }


def direct_call(model: str, instructions: str, input_document: dict[str, Any], schema_path: Path, timeout_seconds: int) -> tuple[dict[str, Any], dict[str, Any], str, str, str, str]:
    prompt = f"{instructions}\nDo not use tools, browse, modify files, or return markdown. Return only the required JSON object.\nSOURCE_JSON:\n{canonical_json(input_document).decode('utf-8')}"
    prompt_sha256 = sha256(prompt.encode("utf-8"))
    started_at = utc_now()
    process = subprocess.run(
        [
            "codex", "-a", "never", "exec", "-m", model,
            "-c", "model_reasoning_effort='low'", "-s", "read-only",
            "--ephemeral", "--ignore-user-config", "--output-schema", str(schema_path), "--json", "-",
        ],
        cwd=ROOT,
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout_seconds + 30,
    )
    finished_at = utc_now()
    if process.returncode != 0:
        raise RuntimeError(f"direct model failed: {process.stderr.strip() or process.stdout.strip()}")
    events = [json.loads(line) for line in process.stdout.splitlines() if line.startswith("{")]
    messages = [event["item"]["text"] for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"]
    completed = [event for event in events if event.get("type") == "turn.completed"]
    if len(messages) != 1 or len(completed) != 1:
        raise ValueError("direct model event shape")
    payload = json.loads(messages[0])
    metadata = {"model": model, "reasoning_effort": "low", "route": "direct-codex-exec", "usage": completed[0].get("usage")}
    return metadata, payload, started_at, finished_at, prompt_sha256, sha256(messages[0].encode("utf-8"))


def run(input_path: Path, output_path: Path, prompt_path: Path, model: str, batch_size: int, start_batch: int, limit_batches: int | None, timeout_seconds: int) -> None:
    source_records = read_jsonl(input_path)
    prompt_document = yaml.safe_load(prompt_path.read_text(encoding="utf-8"))
    prompt_sha = sha256(prompt_path.read_bytes())
    batches = list(enumerate(source_records[start:start + batch_size] for start in range(0, len(source_records), batch_size)))
    total_batches = len(batches)
    batches = batches[start_batch:]
    if limit_batches is not None:
        batches = batches[:limit_batches]
    output_path.mkdir(parents=True, exist_ok=True)

    for index, batch in batches:
        batch_path = output_path / f"batch-{index:03d}"
        batch_path.mkdir(exist_ok=True)
        source_path = batch_path / "source.json"
        result_path = batch_path / "result.json"
        source_document = {"records": batch}
        source_bytes = canonical_json(source_document)
        source_sha = sha256(source_bytes)
        source_path.write_bytes(source_bytes)
        parser_schema_path = batch_path / "parser-schema.json"
        auditor_schema_path = batch_path / "auditor-schema.json"
        parser_schema_path.write_bytes(canonical_json(output_schema(batch, "parser")))
        auditor_schema_path.write_bytes(canonical_json(output_schema(batch, "auditor")))
        if result_path.exists():
            existing = json.loads(result_path.read_text(encoding="utf-8"))
            if existing.get("source_sha256") == source_sha and existing.get("prompt_sha256") == prompt_sha:
                validate_parser(existing["parser"]["payload"], batch)
                validate_auditor(existing["auditor"]["payload"], batch)
                print(f"batch {index + 1}/{total_batches} already complete", flush=True)
                continue
            raise ValueError(f"batch {index} output does not match current input/prompt")

        parser_wrapper, parser_payload, parser_started, parser_finished, parser_input_sha, parser_output_sha = direct_call(
            model, prompt_document["parser"]["instructions"], source_document, parser_schema_path, timeout_seconds
        )
        validate_parser(parser_payload, batch)
        parser_output_path = batch_path / "parser-output.json"
        parser_output_path.write_bytes(canonical_json(parser_payload))

        auditor_input = {"source_records": batch, "parser_output": parser_payload}
        auditor_input_path = batch_path / "auditor-input.json"
        auditor_input_bytes = canonical_json(auditor_input)
        auditor_input_path.write_bytes(auditor_input_bytes)
        auditor_wrapper, auditor_payload, auditor_started, auditor_finished, auditor_prompt_sha, auditor_output_sha = direct_call(
            model, prompt_document["auditor"]["instructions"], auditor_input, auditor_schema_path, timeout_seconds
        )
        validate_auditor(auditor_payload, batch)

        result = {
            "batch": index,
            "source_sha256": source_sha,
            "prompt_sha256": prompt_sha,
            "parser": {
                "prompt_id": prompt_document["parser"]["id"],
                "started_at": parser_started,
                "finished_at": parser_finished,
                "input_sha256": parser_input_sha,
                "output_sha256": parser_output_sha,
                **parser_wrapper,
                "payload": parser_payload,
            },
            "auditor": {
                "prompt_id": prompt_document["auditor"]["id"],
                "started_at": auditor_started,
                "finished_at": auditor_finished,
                "input_sha256": auditor_prompt_sha,
                "output_sha256": auditor_output_sha,
                **auditor_wrapper,
                "payload": auditor_payload,
            },
        }
        result_path.write_bytes(canonical_json(result))
        print(f"batch {index + 1}/{total_batches} complete", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--prompt", type=Path, default=PROMPT_PATH)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--start-batch", type=int, default=0)
    parser.add_argument("--limit-batches", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    arguments = parser.parse_args()
    try:
        run(
            arguments.input.resolve(),
            arguments.output.resolve(),
            arguments.prompt.resolve(),
            arguments.model,
            arguments.batch_size,
            arguments.start_batch,
            arguments.limit_batches,
            arguments.timeout_seconds,
        )
    except (KeyError, OSError, RuntimeError, subprocess.TimeoutExpired, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
