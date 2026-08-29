#!/usr/bin/env python3
"""Verify conservative PMC Open Access availability records."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlparse

import yaml

from verify_repository import validate_schema


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
SCREENING = ISLAND / "screening/2026-08-29"
FULLTEXT = ISLAND / "fulltext/2026-08-30"
SCHEMA = ROOT / "schemas/fulltext-availability.schema.yaml"
REQUEST_SCHEMA = ROOT / "schemas/fulltext-request.schema.yaml"
ID_CONVERTER = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def verify(path: Path = FULLTEXT) -> list[str]:
    errors = []
    try:
        manifest = yaml.safe_load((path / "manifest.yaml").read_text(encoding="utf-8"))["fulltext_availability"]
        records_spec = manifest["records"]
        requests_spec = manifest["requests"]
        records_path = (path / records_spec["path"]).resolve()
        requests_path = (path / requests_spec["path"]).resolve()
        if records_path.parent != path.resolve() or requests_path.parent != path.resolve():
            return ["full-text path escapes run directory"]
        records = read_jsonl(records_path)
        requests = read_jsonl(requests_path)
        schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))
        request_schema = yaml.safe_load(REQUEST_SCHEMA.read_text(encoding="utf-8"))
        if manifest.get("source_screening_manifest_sha256") != sha256(SCREENING / "manifest.yaml"):
            errors.append("full-text source screening hash")
        if sha256(records_path) != records_spec.get("sha256") or len(records) != records_spec.get("count"):
            errors.append("full-text records hash/count")
        if sha256(requests_path) != requests_spec.get("sha256") or len(requests) != requests_spec.get("count"):
            errors.append("full-text requests hash/count")
        for index, record in enumerate(records):
            errors.extend(validate_schema(record, schema, f"availability[{index}]"))
        for index, record in enumerate(requests):
            errors.extend(validate_schema(record, request_schema, f"requests[{index}]"))

        discoveries = {record["id"]: record for record in read_jsonl(SCREENING / "discoveries.jsonl")}
        screenings = [record for record in read_jsonl(SCREENING / "screenings.jsonl") if record["decision"] != "excluded"]
        expected = {
            record["record_id"]: {
                "decision": record["decision"],
                "pmid": discoveries[record["record_id"]]["identifiers"]["pmid"],
            }
            for record in screenings
        }
        expected_ids = set(expected)
        if {record.get("record_id") for record in records} != expected_ids or len(records) != len(expected_ids):
            errors.append("full-text screening coverage")
        pmids = sorted((value["pmid"] for value in expected.values()), key=int)
        position_by_pmid = {pmid: index for index, pmid in enumerate(pmids)}

        request_by_id = {record.get("id"): record for record in requests}
        if len(request_by_id) != len(requests):
            errors.append("duplicate full-text request id")
        expected_batches = {
            "id-converter": [pmids[start:start + 200] for start in range(0, len(pmids), 200)],
            "open-access-filter": [pmids[start:start + 100] for start in range(0, len(pmids), 100)],
        }
        pmc_by_pmid = {}
        oa_pmids = set()
        for request_type, batches in expected_batches.items():
            typed = sorted(
                (record for record in requests if record.get("request_type") == request_type),
                key=lambda record: record.get("page", -1),
            )
            if len(typed) != len(batches):
                errors.append(f"full-text {request_type} request count")
            for page, batch in enumerate(batches):
                request_id = f"{request_type}-{page}"
                request_record = request_by_id.get(request_id)
                if request_record is None or request_record.get("page") != page or request_record.get("requested_pmids") != batch:
                    errors.append(f"full-text {request_type} request coverage")
                    continue
                response_body = request_record.get("response_body", "")
                if hashlib.sha256(response_body.encode("utf-8")).hexdigest() != request_record.get("response_sha256"):
                    errors.append("full-text response hash")
                payload = json.loads(response_body)
                parsed_url = urlparse(request_record.get("request_url", ""))
                parameters = parse_qs(parsed_url.query)
                endpoint = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
                if request_type == "id-converter":
                    if endpoint != ID_CONVERTER or parameters.get("ids") != [",".join(batch)] or parameters.get("idtype") != ["pmid"] or parameters.get("format") != ["json"] or parameters.get("versions") != ["yes"]:
                        errors.append("full-text ID Converter request literal")
                    response_records = payload.get("records", [])
                    response_pmids = [str(item.get("pmid") or item.get("requested-id")) for item in response_records]
                    if len(response_pmids) != len(batch) or set(response_pmids) != set(batch):
                        errors.append("full-text ID Converter response coverage")
                    for item in response_records:
                        pmid = str(item.get("pmid") or item.get("requested-id"))
                        if pmid not in batch:
                            errors.append("full-text ID Converter response coverage")
                        else:
                            pmc_by_pmid[pmid] = item
                else:
                    literal = f"({' OR '.join(f'{pmid}[PMID]' for pmid in batch)}) AND pubmed pmc open access[filter]"
                    if endpoint != ESEARCH or parameters.get("db") != ["pubmed"] or parameters.get("term") != [literal] or parameters.get("retmode") != ["json"] or parameters.get("retmax") != ["100"]:
                        errors.append("full-text Open Access request literal")
                    result = payload["esearchresult"]
                    ids = {str(value) for value in result.get("idlist", [])}
                    if int(result.get("count", 0)) != len(ids) or not ids <= set(batch):
                        errors.append("full-text Open Access response coverage")
                    oa_pmids.update(ids)

        if manifest.get("record_count") != len(records):
            errors.append("full-text manifest count")
        counts = dict(sorted(Counter(record.get("access_status") for record in records).items()))
        if counts != manifest.get("access_counts"):
            errors.append("full-text access counts")
        allowed = sum(record.get("extraction_allowed") is True for record in records)
        if allowed != manifest.get("extraction_allowed"):
            errors.append("full-text allowed count")
        for record in records:
            source = expected.get(record.get("record_id"))
            if source is None:
                continue
            pmid = source["pmid"]
            pmc = pmc_by_pmid.get(pmid, {})
            pmcid = pmc.get("pmcid")
            live = pmc.get("live")
            release_date = pmc.get("release-date")
            is_oa = pmid in oa_pmids
            if pmcid and live is False:
                status = "embargoed"
            elif is_oa and pmcid:
                status = "pmc-open-access"
            elif pmcid:
                status = "pmc-copyrighted-or-unknown"
            else:
                status = "not-in-pmc"
            expected_values = {
                "pmid": pmid,
                "screening_decision": source["decision"],
                "pmcid": pmcid,
                "pmc_live": live,
                "release_date": release_date,
                "open_access_subset": is_oa,
                "access_status": status,
                "extraction_allowed": status == "pmc-open-access",
                "checked_at": manifest.get("checked_at"),
            }
            if any(record.get(key) != value for key, value in expected_values.items()):
                errors.append("full-text source-derived record")
            provenance = record.get("provenance", {})
            expected_id_request = f"id-converter-{position_by_pmid[pmid] // 200}"
            expected_oa_request = f"open-access-filter-{position_by_pmid[pmid] // 100}"
            if provenance.get("id_converter_request_id") != expected_id_request or provenance.get("open_access_request_id") != expected_oa_request:
                errors.append("full-text request trace")
            expected_url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None
            if provenance.get("pmc_url") != expected_url:
                errors.append("full-text PMC URL")
            expected_id = f"https://github.com/Agentic-Health-AI/helse-knowledge/fulltext-availability/pubmed/{pmid}/2026-08-30"
            if record.get("id") != expected_id:
                errors.append("full-text record id")
        if {item.resolve() for item in path.glob("*.jsonl")} != {records_path, requests_path}:
            errors.append("undeclared full-text JSONL")
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        errors.append(f"load error: {error}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fulltext", type=Path, default=FULLTEXT)
    arguments = parser.parse_args()
    errors = verify(arguments.fulltext.resolve())
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Full-text availability verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
