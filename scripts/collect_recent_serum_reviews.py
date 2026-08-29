#!/usr/bin/env python3
"""Collect the frozen recent serum/plasma review corpus and transient PubMed abstracts."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

import yaml

from collect_pubmed_meta_analyses import EFETCH, ESEARCH, ISLAND, ROOT, request, text, utc_now, write_jsonl


SELECTION = ISLAND / "amendments/0.1.2-latest-serum-reviews.yaml"
STORAGE = ISLAND / "amendments/0.1.3-rights-safe-abstracts.yaml"
PROTOCOL = ISLAND / "protocol.yaml"
OUTPUT = ISLAND / "collection/2026-08-30-recent-reviews"
CACHE = ROOT / "generated/pubmed-recent-reviews/abstracts.jsonl"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def ensure_rights_safe_cache(cache: Path) -> None:
    """Reject abstract text inside the repository unless Git ignores it under generated/."""
    try:
        relative = cache.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "generated":
        raise ValueError("abstract cache inside repository must be under generated/")


def xml_date(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    values = [text(element.find(name)) for name in ("Year", "Month", "Day")]
    if not values[0]:
        return None
    return "-".join(value.zfill(2) if index else value for index, value in enumerate(values) if value)


def publication_date(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    year = text(element.find("Year"))
    month = text(element.find("Month"))
    day = text(element.find("Day"))
    if not year:
        match = re.search(r"\b(?:18|19|20)\d{2}\b", text(element.find("MedlineDate")) or "")
        return match.group(0) if match else None
    month_numbers = {name: f"{index:02d}" for index, name in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
    normalized_month = month_numbers.get(month or "", month.zfill(2) if month and month.isdigit() else None)
    if normalized_month and day and day.isdigit():
        return f"{year}-{normalized_month}-{day.zfill(2)}"
    return f"{year}-{normalized_month}" if normalized_month else year


def abstract_text(article: ET.Element) -> str | None:
    parts = []
    for element in article.findall(".//MedlineCitation/Article/Abstract/AbstractText"):
        value = text(element)
        if not value:
            continue
        label = (element.attrib.get("Label") or "").strip()
        parts.append(f"{label}: {value}" if label else value)
    return "\n".join(parts) or None


def parse_article(
    article: ET.Element,
    query_ids: list[str],
    search_run_ids: list[str],
    retrieved_at: str,
    response_sha256: str,
    request_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    citation = article.find("MedlineCitation")
    article_node = citation.find("Article") if citation is not None else None
    pmid = text(citation.find("PMID")) if citation is not None else None
    if citation is None or article_node is None or not pmid:
        raise ValueError("PubMed record lacks citation, article, or PMID")
    abstract = abstract_text(article)
    if abstract is None:
        raise ValueError(f"PubMed query promised an abstract but PMID {pmid} has none")
    abstract_hash = sha256_bytes(abstract.encode("utf-8"))
    authors = []
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
    record_id = f"https://github.com/Agentic-Health-AI/helse-knowledge/discovery/pubmed/recent-serum-reviews/{pmid}"
    record = {
        "id": record_id,
        "record_type": "discovery",
        "study_id": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source": "pubmed",
        "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "search_run_id": search_run_ids[0],
        "query_ids": query_ids,
        "retrieved_at": retrieved_at,
        "title": text(article_node.find("ArticleTitle")),
        "authors": authors,
        "venue": venue,
        "publication_date": publication_date(article_node.find(".//JournalIssue/PubDate")),
        "electronic_publication_date": publication_date(article_node.find("ArticleDate")),
        "state": "discovered",
        "peer_review_status": "unknown",
        "version_status": version_status,
        "identifiers": {"pmid": pmid, "doi": doi, "medrxiv_id": None, "version": None},
        "abstract_sha256": abstract_hash,
        "abstract_character_count": len(abstract),
        "pubmed_revision_date": xml_date(citation.find("DateRevised")),
        "provenance": {
            "collector": "collect_recent_serum_reviews.py/0.1",
            "search_run_ids": search_run_ids,
            "efetch_request_id": request_id,
            "efetch_response_sha256": response_sha256,
            "publication_types": publication_types,
            "abstract_text_committed": False,
            "abstract_normalization": "structured labels joined with colon; sections joined with newline",
        },
    }
    cache_record = {
        "pmid": pmid,
        "retrieved_at": retrieved_at,
        "abstract": abstract,
        "abstract_sha256": abstract_hash,
        "efetch_response_sha256": response_sha256,
    }
    return record, cache_record


def collect(output: Path, cache: Path) -> None:
    ensure_rights_safe_cache(cache)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite collection: {output}")
    selection_document = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
    storage_document = yaml.safe_load(STORAGE.read_text(encoding="utf-8"))
    protocol = yaml.safe_load(PROTOCOL.read_text(encoding="utf-8"))["protocol"]
    queries = selection_document["pubmed"]["query_families"]
    query_order = selection_document["pubmed"]["expected_query_ids"]
    storage_id = storage_document["amendment"]["amendment_id"]
    search_runs = []
    requests = []
    query_ids_by_pmid: dict[str, list[str]] = defaultdict(list)
    search_ids_by_query = {}

    for query_id in query_order:
        query = queries[query_id]
        search_run_id = f"{storage_id}/search-runs/pubmed/{query_id}/2026-08-30"
        search_ids_by_query[query_id] = search_run_id
        raw, url, retrieved_at = request(ESEARCH, {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": "9999",
            "usehistory": "y",
            "tool": "helse_knowledge",
        })
        result = json.loads(raw)["esearchresult"]
        pmids = [str(value) for value in result.get("idlist", [])]
        count = int(result.get("count", 0))
        if count != len(pmids) or count > 9999 or result.get("warninglist"):
            raise ValueError(f"{query_id}: incomplete or warned ESearch response")
        request_id = f"esearch-{query_id}"
        requests.append({
            "id": request_id,
            "record_type": "pubmed-request",
            "request_type": "esearch",
            "request_url": url,
            "retrieved_at": retrieved_at,
            "requested_pmids": [],
            "response_sha256": sha256_bytes(raw),
            "response_body_stored": True,
            "response_body": raw.decode("utf-8"),
        })
        for pmid in pmids:
            query_ids_by_pmid[pmid].append(query_id)
        search_runs.append({
            "id": search_run_id,
            "record_type": "search-run",
            "protocol_id": storage_id,
            "source": "pubmed",
            "query_id": query_id,
            "query_or_endpoint": query,
            "run_status": "executed",
            "date_from": "2021-01-01",
            "date_through": "2026-08-29",
            "executed_at": retrieved_at,
            "retrieved_at": retrieved_at,
            "result_count": count,
            "pagination_log": [{"request_id": request_id, "retstart": 0, "returned": len(pmids)}],
            "provenance": {
                "collector": "collect_recent_serum_reviews.py/0.1",
                "selection_amendment_id": selection_document["amendment"]["amendment_id"],
                "storage_amendment_id": storage_id,
                "query_translation": result.get("querytranslation"),
                "ordered_pmids": pmids,
            },
        })

    pmids = sorted(query_ids_by_pmid, key=int)
    records = []
    cache_records = []
    for page, start in enumerate(range(0, len(pmids), 200)):
        batch = pmids[start:start + 200]
        raw, url, retrieved_at = request(EFETCH, {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "tool": "helse_knowledge",
        })
        response_hash = sha256_bytes(raw)
        request_id = f"efetch-{page}"
        requests.append({
            "id": request_id,
            "record_type": "pubmed-request",
            "request_type": "efetch",
            "request_url": url,
            "retrieved_at": retrieved_at,
            "requested_pmids": batch,
            "response_sha256": response_hash,
            "response_body_stored": False,
            "response_body": None,
        })
        root = ET.fromstring(raw)
        parsed_pmids = set()
        for article in root.findall("PubmedArticle"):
            pmid = text(article.find(".//MedlineCitation/PMID"))
            if not pmid:
                raise ValueError("EFetch record lacks PMID")
            parsed_pmids.add(pmid)
            query_ids = query_ids_by_pmid[pmid]
            search_run_ids = [search_ids_by_query[query_id] for query_id in query_ids]
            record, cache_record = parse_article(article, query_ids, search_run_ids, retrieved_at, response_hash, request_id)
            records.append(record)
            cache_records.append(cache_record)
        if parsed_pmids != set(batch):
            raise ValueError(f"EFetch PMID mismatch on page {page}")

    records.sort(key=lambda record: int(record["identifiers"]["pmid"]))
    cache_records.sort(key=lambda record: int(record["pmid"]))
    with tempfile.TemporaryDirectory(prefix="helse-recent-reviews-", dir=output.parent) as temporary:
        temporary_path = Path(temporary)
        paths = {
            "searches": temporary_path / "search-runs.jsonl",
            "discoveries": temporary_path / "discoveries.jsonl",
            "requests": temporary_path / "requests.jsonl",
        }
        write_jsonl(paths["searches"], search_runs)
        write_jsonl(paths["discoveries"], records)
        write_jsonl(paths["requests"], requests)
        manifest = {
            "collection": {
                "id": f"{storage_id}/collections/2026-08-30-recent-reviews",
                "mode": "discovery-with-transient-abstracts",
                "source": "pubmed",
                "base_protocol_id": protocol["id"],
                "base_protocol_sha256": sha256_path(PROTOCOL),
                "selection_amendment_id": selection_document["amendment"]["amendment_id"],
                "selection_amendment_sha256": sha256_path(SELECTION),
                "storage_amendment_id": storage_id,
                "storage_amendment_sha256": sha256_path(STORAGE),
                "search_cutoff": "2026-08-29",
                "generated_at": utc_now(),
                "query_hits": sum(run["result_count"] for run in search_runs),
                "unique_pmids": len(records),
                "abstracts_fetched": len(cache_records),
                "abstract_text_committed": False,
                "snapshot_notice": "Dated PubMed snapshot; it may not reflect later NLM corrections or updates.",
                "source_acknowledgement": "PubMed data provided by the U.S. National Library of Medicine (NLM). NLM does not endorse this project.",
                "records": {
                    name: {"path": path.name, "sha256": sha256_path(path), "count": len(search_runs if name == "searches" else records if name == "discoveries" else requests)}
                    for name, path in paths.items()
                },
            }
        }
        (temporary_path / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
        cache.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(cache, cache_records)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporary_path), str(output))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--cache", type=Path, default=CACHE)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        collect(arguments.output.resolve(), arguments.cache.resolve())
    except (FileExistsError, KeyError, OSError, RuntimeError, TypeError, ValueError, ET.ParseError, yaml.YAMLError, json.JSONDecodeError) as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    print(f"Collected recent PubMed reviews at {arguments.output.resolve()}")
    print(f"Cached abstract text outside Git at {arguments.cache.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
