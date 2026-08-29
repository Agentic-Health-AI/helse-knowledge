#!/usr/bin/env python3
"""Collect conservative PMC and Open Access availability for non-excluded records."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

import yaml

from collect_pubmed_meta_analyses import ESEARCH, ISLAND, ROOT, request, utc_now, write_jsonl


SCREENING = ISLAND / "screening/2026-08-29"
OUTPUT = ISLAND / "fulltext/2026-08-30"
ID_CONVERTER = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def collect(output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite full-text inventory: {output}")
    discoveries = {record["id"]: record for record in read_jsonl(SCREENING / "discoveries.jsonl")}
    screenings = [record for record in read_jsonl(SCREENING / "screenings.jsonl") if record["decision"] != "excluded"]
    candidates = sorted(
        ({"record_id": record["record_id"], "decision": record["decision"], "pmid": discoveries[record["record_id"]]["identifiers"]["pmid"]} for record in screenings),
        key=lambda item: int(item["pmid"]),
    )
    pmids = [item["pmid"] for item in candidates]
    pmc_by_pmid: dict[str, dict[str, Any]] = {}
    requests = []
    id_request_by_pmid: dict[str, str] = {}
    for page, start in enumerate(range(0, len(pmids), 200)):
        batch = pmids[start:start + 200]
        request_id = f"id-converter-{page}"
        raw, url, retrieved_at = request(ID_CONVERTER, {
            "ids": ",".join(batch),
            "idtype": "pmid",
            "format": "json",
            "versions": "yes",
            "tool": "helse_knowledge",
        })
        payload = json.loads(raw)
        for record in payload.get("records", []):
            pmid = str(record.get("pmid") or record.get("requested-id"))
            if pmid:
                pmc_by_pmid[pmid] = record
        for pmid in batch:
            id_request_by_pmid[pmid] = request_id
        requests.append({
            "id": request_id,
            "record_type": "fulltext-request",
            "request_type": "id-converter",
            "page": page,
            "request_url": url,
            "retrieved_at": retrieved_at,
            "requested_pmids": batch,
            "response_sha256": sha256_bytes(raw),
            "response_body": raw.decode("utf-8"),
        })

    oa_pmids: set[str] = set()
    oa_request_by_pmid: dict[str, str] = {}
    for page, start in enumerate(range(0, len(pmids), 100)):
        batch = pmids[start:start + 100]
        request_id = f"open-access-filter-{page}"
        term = f"({' OR '.join(f'{pmid}[PMID]' for pmid in batch)}) AND pubmed pmc open access[filter]"
        raw, url, retrieved_at = request(ESEARCH, {
            "db": "pubmed",
            "term": term,
            "retmode": "json",
            "retmax": "100",
        })
        result = json.loads(raw)["esearchresult"]
        ids = {str(value) for value in result.get("idlist", [])}
        if int(result.get("count", 0)) != len(ids):
            raise ValueError("incomplete PMC Open Access filter retrieval")
        oa_pmids.update(ids)
        for pmid in batch:
            oa_request_by_pmid[pmid] = request_id
        requests.append({
            "id": request_id,
            "record_type": "fulltext-request",
            "request_type": "open-access-filter",
            "page": page,
            "request_url": url,
            "retrieved_at": retrieved_at,
            "requested_pmids": batch,
            "response_sha256": sha256_bytes(raw),
            "response_body": raw.decode("utf-8"),
        })

    checked_at = utc_now()
    records = []
    for candidate in candidates:
        pmid = candidate["pmid"]
        pmc = pmc_by_pmid.get(pmid, {})
        pmcid = pmc.get("pmcid")
        live = pmc.get("live")
        release_date = pmc.get("release-date")
        is_oa = pmid in oa_pmids
        if is_oa and not pmcid:
            raise ValueError(f"PMC Open Access PMID lacks PMCID: {pmid}")
        if pmcid and live is False:
            access_status = "embargoed"
        elif is_oa:
            access_status = "pmc-open-access"
        elif pmcid:
            access_status = "pmc-copyrighted-or-unknown"
        else:
            access_status = "not-in-pmc"
        records.append({
            "id": f"https://github.com/Agentic-Health-AI/helse-knowledge/fulltext-availability/pubmed/{pmid}/2026-08-30",
            "record_type": "fulltext-availability",
            "record_id": candidate["record_id"],
            "pmid": pmid,
            "screening_decision": candidate["decision"],
            "pmcid": pmcid,
            "pmc_live": live,
            "release_date": release_date,
            "open_access_subset": is_oa,
            "access_status": access_status,
            "extraction_allowed": access_status == "pmc-open-access",
            "checked_at": checked_at,
            "provenance": {
                "id_converter": ID_CONVERTER,
                "id_converter_request_id": id_request_by_pmid[pmid],
                "open_access_filter": "pubmed pmc open access[filter]",
                "open_access_request_id": oa_request_by_pmid[pmid],
                "pmc_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/" if pmcid else None,
            },
        })

    with tempfile.TemporaryDirectory(prefix="helse-fulltext-", dir=output.parent) as temporary:
        temporary_path = Path(temporary)
        records_path = temporary_path / "availability.jsonl"
        requests_path = temporary_path / "requests.jsonl"
        write_jsonl(records_path, records)
        write_jsonl(requests_path, requests)
        counts = Counter(record["access_status"] for record in records)
        manifest = {
            "fulltext_availability": {
                "id": "https://github.com/Agentic-Health-AI/helse-knowledge/fulltext-availability/2026-08-30",
                "source_screening_manifest_sha256": sha256_path(SCREENING / "manifest.yaml"),
                "checked_at": checked_at,
                "record_count": len(records),
                "access_counts": dict(sorted(counts.items())),
                "extraction_allowed": sum(record["extraction_allowed"] for record in records),
                "records": {"path": records_path.name, "sha256": sha256_path(records_path), "count": len(records)},
                "requests": {"path": requests_path.name, "sha256": sha256_path(requests_path), "count": len(requests)},
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
        collect(arguments.output.resolve())
    except (FileExistsError, KeyError, OSError, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Collected full-text availability at {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
