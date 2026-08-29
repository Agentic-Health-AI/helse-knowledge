#!/usr/bin/env python3
"""Validate canonical Helse Evidence contracts and their synthetic proof corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
ISLAND_REL = Path("measurements/vitamin-d-25-oh")
MANIFEST_REL = ISLAND_REL / "corpus-manifest.yaml"
AMENDMENT_REL = ISLAND_REL / "amendments/0.1.1-meta-analysis-pilot.yaml"
EXPECTED_PIN = {
    "upstream_version": "0.2",
    "repository": "https://github.com/GoogleCloudPlatform/knowledge-catalog",
    "specification_path": "okf/SPEC.md",
    "resolved_commit": "02317b819c9602fca7cbaa565c215144cef98fe8",
    "sha256": "26aa5da029278939f914e578107242d9607d4f2dc5fe153272b82f9ed1030101",
}
EXPECTED_QUESTION_IDS = {
    "q1-measurement",
    "q2-distribution",
    "q3-association",
    "q4-intervention",
    "q5-harm",
    "q6-disagreement",
}
EXPECTED_QUERY_IDS = {
    "q1-measurement",
    "q2-distribution",
    "q3-association",
    "q4-intervention",
    "q5-high-measured-level",
    "q5-supplementation-harm",
    "q6-disagreement-context",
}
TYPE_CHECKS = {
    "array": list,
    "boolean": bool,
    "integer": int,
    "number": (int, float),
    "object": dict,
    "string": str,
}
FORBIDDEN_KEY_FRAGMENTS = {
    "patientid",
    "personid",
    "personname",
    "cpr",
    "medicalrecord",
    "healthrecord",
    "privateclinicalrecord",
    "credential",
    "password",
    "accesstoken",
    "apikey",
    "secretkey",
}
PRIVATE_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~-]{8,}\b", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b\d{6}[- ]?\d{4}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
)
GENERATED_REFERENCE = re.compile(r"(?:^|/)generated/|\.(?:db|sqlite|embedding)(?:$|[?#])", re.I)


def read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be an object")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: record must be an object")
        records.append(value)
    return records


def resolve_inside(root: Path, base: Path, raw_path: str) -> Path:
    path = (base / raw_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes repository: {raw_path}") from error
    return path


def load_bundle(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    island = root / ISLAND_REL
    manifest_document = read_yaml(root / MANIFEST_REL)
    manifest = manifest_document.get("manifest")
    if not isinstance(manifest, dict):
        raise ValueError("manifest document must contain a manifest object")

    bundle: dict[str, Any] = {
        "root": root,
        "island": island,
        "manifest": manifest,
        "protocol": read_yaml(resolve_inside(root, island, manifest["protocol"]))["protocol"],
        "amendment": read_yaml(root / AMENDMENT_REL),
        "profile": read_yaml(resolve_inside(root, island, manifest["profile"])),
        "pin": read_yaml(resolve_inside(root, island, manifest["okf_pin"])),
        "schemas": {},
        "collections": {},
        "record_paths": {},
    }
    for collection_name, spec in manifest.get("records", {}).items():
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str) or not isinstance(spec.get("schema"), str):
            raise ValueError(f"manifest record entry {collection_name} is invalid")
        record_path = resolve_inside(root, island, spec["path"])
        schema_path = resolve_inside(root, island, spec["schema"])
        bundle["collections"][collection_name] = read_jsonl(record_path)
        bundle["schemas"][collection_name] = read_yaml(schema_path)
        bundle["record_paths"][collection_name] = record_path
    return bundle


def walk(value: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}" if path else str(key)
            yield child, item
            yield from walk(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child = f"{path}[{index}]"
            yield child, item
            yield from walk(item, child)
    else:
        yield path, value


def validate_schema(record: dict[str, Any], schema: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("record_type")
    if record.get("record_type") != expected_type:
        errors.append(f"schema violation: {label} record_type")
    for field in schema.get("required", []):
        if field not in record:
            errors.append(f"schema violation: {label} missing {field}")
    for field, type_name in schema.get("types", {}).items():
        value = record.get(field)
        expected = TYPE_CHECKS.get(type_name)
        if value is not None and expected is not None and (not isinstance(value, expected) or type_name == "integer" and isinstance(value, bool)):
            errors.append(f"schema violation: {label} {field} type")
    for field, allowed in schema.get("enums", {}).items():
        if record.get(field) is not None and record.get(field) not in allowed:
            errors.append(f"schema violation: {label} {field} enum")
    return errors


def validate_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def fail(message: str) -> None:
        errors.append(message)

    manifest = bundle["manifest"]
    protocol = bundle["protocol"]
    amendment_document = bundle["amendment"]
    profile = bundle["profile"]
    pin = bundle["pin"].get("pin", {})
    collections = bundle["collections"]
    schemas = bundle["schemas"]

    required_collections = {"searches", "discoveries", "screenings", "relations", "extractions", "verification_events", "syntheses", "claims"}
    if set(collections) != required_collections:
        fail("manifest must declare every canonical record collection exactly once")
    listed_jsonl = {path.resolve() for path in bundle["record_paths"].values()}
    actual_jsonl = {path for path in bundle["island"].rglob("*.jsonl") if "collection" not in path.parts}
    if listed_jsonl != actual_jsonl:
        fail("unlisted canonical JSONL file")
    if manifest.get("generated_artifacts_required") is not False:
        fail("canonical dependence on generated artifacts")
    for path in listed_jsonl:
        if "generated" in path.parts:
            fail("canonical dependence on generated artifacts")

    for key, expected in EXPECTED_PIN.items():
        if pin.get(key) != expected:
            fail(f"OKF pin mismatch: {key}")
    extends = profile.get("extends", {})
    if extends.get("okf_pin_id") != pin.get("id") or extends.get("local_pin_path") != "okf-0.2-pin.yaml":
        fail("pin/profile separation")
    if "upstream_okf" in profile:
        fail("profile duplicates upstream OKF pin")
    verification_policy = profile.get("verification", {})
    if verification_policy.get("human_approval_gates") != "forbidden":
        fail("human approval gate is not forbidden")
    if profile.get("canonical_formats", {}).get("generated_artifacts_are_canonical") is not False:
        fail("canonical dependence on generated artifacts")

    required_protocol = {"id", "version", "status", "protocol_owner", "proposed_at", "frozen_at", "search_cutoff", "collection_allowed", "analyte", "scope", "questions", "eligibility", "discovery", "screening", "relations", "extraction", "llm_processing", "risk_of_bias_rules", "synthesis", "amendment_policy"}
    if not required_protocol <= set(protocol):
        fail("protocol completeness")
    if protocol.get("status") != "frozen" or protocol.get("collection_allowed") is not True:
        fail("protocol freeze gate")

    amendment = amendment_document.get("amendment", {})
    amendment_scope = amendment_document.get("scope", {})
    amendment_pubmed = amendment_document.get("pubmed", {})
    base_protocol_hash = hashlib.sha256((bundle["island"] / "protocol.yaml").read_bytes()).hexdigest()
    if amendment.get("status") != "frozen" or amendment.get("base_protocol_id") != protocol.get("id"):
        fail("active protocol amendment identity")
    if amendment.get("input_hashes", {}).get("protocol.yaml") != base_protocol_hash:
        fail("active protocol amendment base hash")
    required_amendment_fields = set(protocol.get("amendment_policy", {}).get("required_fields", []))
    if not required_amendment_fields <= set(amendment):
        fail("active protocol amendment completeness")
    if amendment_scope.get("sources") != ["pubmed"] or amendment_scope.get("q6_disagreement") != "derived-from-included-q1-q5-records":
        fail("active protocol amendment scope")
    narrow_query_ids = EXPECTED_QUERY_IDS - {"q6-disagreement-context"}
    narrow_queries = amendment_pubmed.get("query_families", {})
    if set(narrow_queries) != narrow_query_ids or set(amendment_pubmed.get("expected_query_ids", [])) != narrow_query_ids:
        fail("active protocol amendment query set")
    required_analyte_terms = ('"Calcifediol"[MeSH Terms]', '"25-hydroxyvitamin D"[Title/Abstract]', '"25(OH)D"[Title/Abstract]')
    for query_id, query in narrow_queries.items():
        if '"Vitamin D"[MeSH Terms] OR "Calcifediol"[MeSH Terms]' in query:
            fail(f"active query has broad analyte branch: {query_id}")
        if not all(term in query for term in required_analyte_terms):
            fail(f"active query lacks 25(OH)D core: {query_id}")
        if '("Meta-Analysis"[Publication Type] OR meta-analy*[Title])' not in query:
            fail(f"active query lacks meta-analysis gate: {query_id}")
        if "2026/08/29[Date - Publication]" not in query:
            fail(f"active query lacks frozen cutoff: {query_id}")
    llm_policy = protocol.get("llm_processing", {})
    if llm_policy.get("human_fallback") != "forbidden" or not llm_policy.get("required_run_provenance"):
        fail("LLM processing policy incomplete")
    questions = {item.get("id"): item for item in protocol.get("questions", []) if isinstance(item, dict)}
    if set(questions) != EXPECTED_QUESTION_IDS:
        fail("protocol question set")
    question_fields = {"question", "population", "settings", "exposure_or_intervention", "comparators", "outcomes", "eligible_designs"}
    for question_id, question in questions.items():
        if any(not question.get(field) for field in question_fields):
            fail(f"protocol question incomplete: {question_id}")
    queries = protocol.get("discovery", {}).get("pubmed", {}).get("query_families", {})
    if set(queries) != EXPECTED_QUERY_IDS:
        fail("PubMed query family set")
    for query_id, query in queries.items():
        if "2026/08/29[Date - Publication]" not in query:
            fail(f"PubMed query lacks frozen cutoff: {query_id}")
        if query_id != "q5-supplementation-harm" and not all(term in query for term in ("calcidiol", "calcifediol")):
            fail(f"PubMed query lacks analyte synonyms: {query_id}")
    intervention_query = queries.get("q4-intervention", "")
    if not all(term in intervention_query for term in ("cholecalciferol", "ergocalciferol")):
        fail("PubMed intervention query lacks supplement synonyms")
    medrxiv = protocol.get("discovery", {}).get("medrxiv", {})
    if medrxiv.get("endpoint") != "https://api.biorxiv.org/details/medrxiv/2019-06-25/2026-08-29/{cursor}/json":
        fail("medRxiv endpoint mismatch")
    if not medrxiv.get("local_filter", {}).get("frozen") or not medrxiv.get("local_filter", {}).get("regex"):
        fail("medRxiv local filter not frozen")

    all_ids: dict[str, str] = {}
    for collection_name, records in collections.items():
        schema = schemas.get(collection_name, {})
        if schema.get("version") != profile.get("schemas", {}).get("version"):
            fail(f"schema version mismatch: {collection_name}")
        for index, record in enumerate(records):
            label = f"{collection_name}[{index}]"
            errors.extend(validate_schema(record, schema, label))
            record_id = record.get("id")
            if isinstance(record_id, str):
                if record_id in all_ids:
                    fail("duplicate canonical id")
                all_ids[record_id] = label

    searches = {item["id"]: item for item in collections["searches"] if isinstance(item.get("id"), str)}
    records = {item["id"]: item for item in collections["discoveries"] if isinstance(item.get("id"), str)}
    screenings = {item["record_id"]: item for item in collections["screenings"] if isinstance(item.get("record_id"), str)}
    events = {item["id"]: item for item in collections["verification_events"] if isinstance(item.get("id"), str)}
    extractions = {item["id"]: item for item in collections["extractions"] if isinstance(item.get("id"), str)}
    syntheses = {item["id"]: item for item in collections["syntheses"] if isinstance(item.get("id"), str)}

    for search in searches.values():
        if search.get("protocol_id") != protocol.get("id"):
            fail("search protocol mismatch")
        query_id = search.get("query_id")
        if search.get("source") == "pubmed" and query_id not in EXPECTED_QUERY_IDS:
            fail("search query id unknown")
        if search.get("source") == "medrxiv" and query_id != "local-analyte-filter":
            fail("search query id unknown")
        if search.get("run_status") == "executed":
            for field in schemas["searches"].get("executed_requires_non_null", []):
                if search.get(field) is None:
                    fail(f"executed search missing {field}")

    allowed_transitions = {tuple(pair) for pair in protocol.get("screening", {}).get("allowed_transitions", [])}
    controlled_reasons = set(protocol.get("eligibility", {}).get("controlled_exclusion_reasons", []))
    for record in records.values():
        if not record.get("source_url") or record.get("search_run_id") not in searches:
            fail("missing search/source trace")
        search = searches.get(record.get("search_run_id"))
        if search and any(query_id != search.get("query_id") for query_id in record.get("query_ids", [])):
            fail("record query trace mismatch")
        if record.get("source") == "medrxiv" and record.get("peer_review_status") != "preprint":
            fail("preprint labelled peer-reviewed")
        if record.get("version_status") == "preprint-version" and record.get("peer_review_status") != "preprint":
            fail("preprint labelled peer-reviewed")
        if record.get("state") in {"included", "excluded", "duplicate", "superseded-by-publication", "retracted"} and record.get("id") not in screenings:
            fail("screened state without screening decision")

    for record_id, screening in screenings.items():
        record = records.get(record_id)
        if record is None:
            fail("screening references missing record")
            continue
        history = screening.get("state_history", [])
        if not history or history[0] != "discovered" or history[-1] != record.get("state"):
            fail("invalid state history")
        for transition in zip(history, history[1:]):
            if transition not in allowed_transitions:
                fail("invalid state transition")
        decision = screening.get("decision")
        expected_decisions = {
            "included": "included",
            "superseded-by-publication": "included",
            "retracted": "included",
            "excluded": "excluded",
            "duplicate": "duplicate",
            "awaiting-full-text": "awaiting-full-text",
        }
        if expected_decisions.get(record.get("state")) != decision:
            fail("screening decision conflicts with record state")
        reason = screening.get("exclusion_reason")
        if decision == "excluded" and reason not in controlled_reasons:
            fail("exclusion without controlled reason")
        if decision != "excluded" and decision != "duplicate" and reason is not None:
            fail("unexpected exclusion reason")
        if not screening.get("evaluation_events"):
            fail("screening lacks review event")
        for event_id in screening.get("evaluation_events", []):
            event = events.get(event_id)
            if event is None or event.get("target_id") != screening.get("id"):
                fail("broken screening event reference")

    allowed_actor_types = {"llm", "validator"}
    required_llm_provenance = set(protocol.get("llm_processing", {}).get("required_run_provenance", []))
    for event in events.values():
        if event.get("actor_type") not in allowed_actor_types:
            fail("forbidden verification actor type")
        if event.get("actor_type") == "llm" and not required_llm_provenance <= set(event.get("provenance", {})):
            fail("LLM event missing reproducibility provenance")
        if event.get("target_id") not in all_ids:
            fail("verification event target missing")

    for relation in collections["relations"]:
        source = records.get(relation.get("from_id"))
        target = records.get(relation.get("to_id"))
        if source is None or target is None or source is target:
            fail("broken relation reference")
            continue
        relation_type = relation.get("relation_type")
        if relation_type == "duplicate-candidate" and relation.get("auto_merged"):
            fail("candidate auto-merge")
        if relation_type in {"preprint-version-of", "final-publication-of"} and source.get("study_id") != target.get("study_id"):
            fail("preprint/final study identity mismatch")
        if relation_type == "retraction-of" and (source.get("version_status") != "retraction-notice" or target.get("state") != "retracted"):
            fail("invalid retraction relation")
        if relation_type == "correction-of" and source.get("version_status") != "correction-notice":
            fail("invalid correction relation")

    for extraction in extractions.values():
        record = records.get(extraction.get("record_id"))
        if record is None or record.get("state") != "included" or screenings.get(record.get("id"), {}).get("decision") != "included":
            fail("extraction from non-included record")
        if extraction.get("question_id") not in EXPECTED_QUESTION_IDS:
            fail("unknown extraction question")
        if not extraction.get("source_locations"):
            fail("missing extraction source location")
        for event_id in extraction.get("verification_events", []):
            event = events.get(event_id)
            if event is None or event.get("target_id") != extraction.get("id"):
                fail("broken extraction event reference")

    retracted_record_ids = {record_id for record_id, record in records.items() if record.get("state") == "retracted"}
    for synthesis in syntheses.values():
        if synthesis.get("question_id") not in EXPECTED_QUESTION_IDS:
            fail("unknown synthesis question")
        evidence_ids = synthesis.get("evidence_ids", [])
        if synthesis.get("conclusion_status") in {"draft", "stable"} and not evidence_ids:
            fail("conclusion lacks evidence")
        if any(evidence_id not in extractions for evidence_id in evidence_ids):
            fail("broken synthesis evidence reference")
        evidence_records = [records.get(extractions[evidence_id].get("record_id")) for evidence_id in evidence_ids if evidence_id in extractions]
        evidence_records = [record for record in evidence_records if record is not None]
        if any(record.get("state") != "included" for record in evidence_records):
            fail("synthesis uses non-included evidence")
        study_ids = [record.get("study_id") for record in evidence_records]
        if len(study_ids) != len(set(study_ids)):
            fail("preprint/final double-counting")
        if synthesis.get("conclusion_status") == "stable" and evidence_records and all(record.get("peer_review_status") == "preprint" for record in evidence_records):
            fail("stable conclusion from preprints only")
        if any(evidence_id not in extractions for evidence_id in synthesis.get("emerging_evidence_ids", [])):
            fail("broken emerging evidence reference")

    numeric_context = schemas["claims"].get("numeric_requires", [])
    for claim in collections["claims"]:
        synthesis = syntheses.get(claim.get("synthesis_id"))
        evidence_ids = claim.get("evidence_ids", [])
        if synthesis is None or any(evidence_id not in extractions for evidence_id in evidence_ids):
            fail("broken claim references")
        elif not set(evidence_ids) <= set(synthesis.get("evidence_ids", [])):
            fail("claim evidence not in synthesis")
        if isinstance(claim.get("numeric_value"), (int, float)) and not isinstance(claim.get("numeric_value"), bool):
            if any(claim.get(field) in (None, "", {}) for field in numeric_context):
                fail("numeric claim without required context")
        if claim.get("status") == "active":
            if synthesis is None or synthesis.get("conclusion_status") != "stable":
                fail("active claim lacks stable synthesis")
            supporting_records = {extractions[evidence_id].get("record_id") for evidence_id in evidence_ids if evidence_id in extractions}
            if supporting_records & retracted_record_ids:
                fail("active claim supported by retraction")

    for collection_name, value in collections.items():
        for path, item in walk(value, collection_name):
            key = re.sub(r"[^a-z0-9]", "", path.rsplit(".", 1)[-1].split("[", 1)[0].casefold())
            if any(fragment in key for fragment in FORBIDDEN_KEY_FRAGMENTS):
                fail("forbidden personal/private structured field")
            if isinstance(item, str):
                if any(pattern.search(item) for pattern in PRIVATE_VALUE_PATTERNS):
                    fail("forbidden personal/private value or credential")
                if GENERATED_REFERENCE.search(item):
                    fail("canonical dependence on generated artifacts")

    if manifest.get("mode") == "synthetic-fixture":
        for collection_name, items in collections.items():
            for item in items:
                if not str(item.get("id", "")).startswith("https://example.invalid/"):
                    fail(f"synthetic fixture id outside reserved namespace: {collection_name}")
        for record in records.values():
            if record.get("authors") or not str(record.get("source_url", "")).startswith("https://example.invalid/"):
                fail("synthetic discovery contains non-synthetic source metadata")

    return sorted(set(errors))


def validate(root: Path = ROOT) -> list[str]:
    try:
        return validate_bundle(load_bundle(root))
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError) as error:
        return [f"load error: {error}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    arguments = parser.parse_args()
    errors = validate(arguments.root)
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Helse corpus contract verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
