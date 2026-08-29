#!/usr/bin/env python3
"""Collect the frozen 25(OH)D meta-analysis PubMed discovery corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import yaml


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
PROTOCOL_PATH = ISLAND / "protocol.yaml"
AMENDMENT_PATH = ISLAND / "amendments/0.1.1-meta-analysis-pilot.yaml"
OUTPUT_PATH = ISLAND / "collection/2026-08-29"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "helse-knowledge/0.1 (https://github.com/Agentic-Health-AI/helse-knowledge)"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def request(endpoint: str, parameters: dict[str, str]) -> tuple[bytes, str, str]:
    url = f"{endpoint}?{urlencode(parameters)}"
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
                value = response.read()
            time.sleep(0.35)
            return value, url, utc_now()
        except Exception as error:  # network errors are reported after bounded retries
            last_error = error
            time.sleep(2**attempt)
    raise RuntimeError(f"request failed after three attempts: {url}: {last_error}")


def text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def publication_date(citation: ET.Element) -> str | None:
    date = citation.find(".//Article/ArticleDate")
    if date is None:
        date = citation.find(".//JournalIssue/PubDate")
    if date is None:
        return None
    year = text(date.find("Year"))
    month = text(date.find("Month"))
    day = text(date.find("Day"))
    if year:
        month_numbers = {name: f"{index:02d}" for index, name in enumerate(
            ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
        )}
        normalized_month = month_numbers.get(month or "", month.zfill(2) if month and month.isdigit() else None)
        if normalized_month and day and day.isdigit():
            return f"{year}-{normalized_month}-{day.zfill(2)}"
        if normalized_month:
            return f"{year}-{normalized_month}"
        return year
    medline_date = text(date.find("MedlineDate"))
    match = re.search(r"\b(?:18|19|20)\d{2}\b", medline_date or "")
    return match.group(0) if match else None


def parse_article(article: ET.Element, query_id: str, search_run_id: str, retrieved_at: str, response_sha256: str) -> dict[str, Any]:
    citation = article.find("MedlineCitation")
    if citation is None:
        raise ValueError("PubMed record lacks MedlineCitation")
    pmid = text(citation.find("PMID"))
    if not pmid:
        raise ValueError("PubMed record lacks PMID")
    article_node = citation.find("Article")
    if article_node is None:
        raise ValueError(f"PMID {pmid} lacks Article")

    authors: list[str] = []
    for author in article_node.findall(".//AuthorList/Author"):
        collective = text(author.find("CollectiveName"))
        name = " ".join(filter(None, (text(author.find("ForeName")), text(author.find("LastName")))))
        if collective or name:
            authors.append(collective or name)

    doi = None
    for identifier in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if identifier.attrib.get("IdType") == "doi":
            doi = text(identifier)
            break

    publication_types = [value for value in (text(item) for item in article_node.findall(".//PublicationTypeList/PublicationType")) if value]
    lowered_types = {value.casefold() for value in publication_types}
    if "retraction of publication" in lowered_types:
        version_status = "retraction-notice"
    elif "published erratum" in lowered_types:
        version_status = "correction-notice"
    else:
        version_status = "final-publication"

    venue = text(article_node.find(".//Journal/Title")) or text(citation.find("MedlineJournalInfo/MedlineTA"))
    canonical_base = "https://github.com/Agentic-Health-AI/helse-knowledge"
    return {
        "id": f"{canonical_base}/discovery/pubmed/{query_id}/{pmid}",
        "record_type": "discovery",
        "study_id": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source": "pubmed",
        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "search_run_id": search_run_id,
        "query_ids": [query_id],
        "retrieved_at": retrieved_at,
        "title": text(article_node.find("ArticleTitle")),
        "authors": authors,
        "venue": venue,
        "publication_date": publication_date(citation),
        "state": "discovered",
        "peer_review_status": "unknown",
        "version_status": version_status,
        "identifiers": {"pmid": pmid, "doi": doi, "medrxiv_id": None, "version": None},
        "provenance": {
            "collector": "collect_pubmed_meta_analyses.py/0.1",
            "efetch_response_sha256": response_sha256,
            "publication_types": publication_types,
        },
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
            handle.write("\n")


def collect(output_path: Path) -> None:
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite existing collection: {output_path}")

    protocol = yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))["protocol"]
    amendment_document = yaml.safe_load(AMENDMENT_PATH.read_text(encoding="utf-8"))
    amendment = amendment_document["amendment"]
    queries = amendment_document["pubmed"]["query_families"]
    search_runs: list[dict[str, Any]] = []
    discoveries: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="helse-collection-", dir=output_path.parent) as temporary:
        temporary_path = Path(temporary)
        for query_id in amendment_document["pubmed"]["expected_query_ids"]:
            query = queries[query_id]
            search_run_id = f"{amendment['amendment_id']}/search-runs/pubmed/{query_id}/2026-08-29"
            raw_search, search_url, search_retrieved_at = request(ESEARCH, {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": "9999",
                "usehistory": "y",
            })
            search_response = json.loads(raw_search)
            result = search_response["esearchresult"]
            count = int(result["count"])
            pmids = result["idlist"]
            if count != len(pmids) or count > 9999:
                raise ValueError(f"{query_id}: incomplete ESearch retrieval: count={count}, ids={len(pmids)}")

            pagination_log: list[dict[str, Any]] = [{
                "kind": "esearch",
                "endpoint": ESEARCH,
                "request_url": search_url,
                "retrieved_at": search_retrieved_at,
                "response_sha256": sha256_bytes(raw_search),
                "returned": len(pmids),
            }]
            query_records: dict[str, dict[str, Any]] = {}
            for page, start in enumerate(range(0, len(pmids), 200)):
                batch = pmids[start:start + 200]
                raw_fetch, _, fetch_retrieved_at = request(EFETCH, {
                    "db": "pubmed",
                    "id": ",".join(batch),
                    "retmode": "xml",
                })
                response_hash = sha256_bytes(raw_fetch)
                root = ET.fromstring(raw_fetch)
                parsed = [parse_article(article, query_id, search_run_id, fetch_retrieved_at, response_hash) for article in root.findall("PubmedArticle")]
                parsed_pmids = {record["identifiers"]["pmid"] for record in parsed}
                if parsed_pmids != set(batch):
                    raise ValueError(f"{query_id}: EFetch PMID mismatch on page {page}")
                query_records.update({record["identifiers"]["pmid"]: record for record in parsed})
                pagination_log.append({
                    "kind": "efetch",
                    "endpoint": EFETCH,
                    "page": page,
                    "retrieved_at": fetch_retrieved_at,
                    "requested": len(batch),
                    "pmids_sha256": sha256_bytes("\n".join(batch).encode("utf-8")),
                    "response_sha256": response_hash,
                })

            discoveries.extend(query_records[pmid] for pmid in pmids)
            search_runs.append({
                "id": search_run_id,
                "record_type": "search-run",
                "protocol_id": amendment["amendment_id"],
                "source": "pubmed",
                "query_id": query_id,
                "query_or_endpoint": query,
                "run_status": "executed",
                "date_from": "1900-01-01",
                "date_through": "2026-08-29",
                "executed_at": pagination_log[0]["retrieved_at"],
                "retrieved_at": pagination_log[-1]["retrieved_at"],
                "result_count": count,
                "pagination_log": pagination_log,
                "provenance": {
                    "collector": "collect_pubmed_meta_analyses.py/0.1",
                    "base_protocol_id": protocol["id"],
                    "amendment_id": amendment["amendment_id"],
                    "query_translation": result.get("querytranslation"),
                    "warnings": result.get("warninglist", {}),
                },
            })

        search_path = temporary_path / "search-runs.jsonl"
        discovery_path = temporary_path / "discoveries.jsonl"
        write_jsonl(search_path, search_runs)
        write_jsonl(discovery_path, discoveries)
        unique_pmids = {record["identifiers"]["pmid"] for record in discoveries}
        manifest = {
            "collection": {
                "id": f"{amendment['amendment_id']}/collections/2026-08-29",
                "mode": "discovery-only",
                "source": "pubmed",
                "base_protocol_id": protocol["id"],
                "base_protocol_sha256": sha256_path(PROTOCOL_PATH),
                "amendment_id": amendment["amendment_id"],
                "amendment_sha256": sha256_path(AMENDMENT_PATH),
                "search_cutoff": "2026-08-29",
                "generated_at": utc_now(),
                "query_result_records": len(discoveries),
                "unique_pmids": len(unique_pmids),
                "records": {
                    "searches": {"path": "search-runs.jsonl", "sha256": sha256_path(search_path), "count": len(search_runs)},
                    "discoveries": {"path": "discoveries.jsonl", "sha256": sha256_path(discovery_path), "count": len(discoveries)},
                },
            }
        }
        (temporary_path / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_path), str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        collect(arguments.output.resolve())
    except (FileExistsError, KeyError, OSError, RuntimeError, ValueError, ET.ParseError, yaml.YAMLError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Collected PubMed discovery corpus at {arguments.output.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
