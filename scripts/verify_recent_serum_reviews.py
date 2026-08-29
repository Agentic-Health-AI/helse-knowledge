#!/usr/bin/env python3
"""Verify the frozen recent serum/plasma PubMed review collection."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import yaml

from verify_repository import validate_schema


ROOT = Path(__file__).resolve().parents[1]
ISLAND = ROOT / "measurements/vitamin-d-25-oh"
PROTOCOL = ISLAND / "protocol.yaml"
SELECTION = ISLAND / "amendments/0.1.2-latest-serum-reviews.yaml"
STORAGE = ISLAND / "amendments/0.1.3-rights-safe-abstracts.yaml"
COLLECTION = ISLAND / "collection/2026-08-30-recent-reviews"
CACHE = ROOT / "generated/pubmed-recent-reviews/abstracts.jsonl"
SEARCH_SCHEMA = ROOT / "schemas/search-run.schema.yaml"
DISCOVERY_SCHEMA = ROOT / "schemas/discovery.schema.yaml"
REQUEST_SCHEMA = ROOT / "schemas/pubmed-request.schema.yaml"
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "helse-knowledge/0.1 (https://github.com/Agentic-Health-AI/helse-knowledge)"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def element_text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def parsed_date(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    year = element_text(element.find("Year"))
    month = element_text(element.find("Month"))
    day = element_text(element.find("Day"))
    if not year:
        match = re.search(r"\b(?:18|19|20)\d{2}\b", element_text(element.find("MedlineDate")) or "")
        return match.group(0) if match else None
    month_numbers = {name: f"{index:02d}" for index, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )}
    normalized_month = month_numbers.get(month or "", month.zfill(2) if month and month.isdigit() else None)
    if normalized_month and day and day.isdigit():
        return f"{year}-{normalized_month}-{day.zfill(2)}"
    return f"{year}-{normalized_month}" if normalized_month else year


def parsed_revision_date(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    values = [element_text(element.find(name)) for name in ("Year", "Month", "Day")]
    if not values[0]:
        return None
    return "-".join(value.zfill(2) if index else value for index, value in enumerate(values) if value)


def parse_source_article(article: ET.Element) -> dict:
    citation = article.find("MedlineCitation")
    article_node = citation.find("Article") if citation is not None else None
    pmid = element_text(citation.find("PMID")) if citation is not None else None
    if citation is None or article_node is None or not pmid:
        raise ValueError("refetched PubMed article lacks citation, article, or PMID")
    abstract_parts = []
    for element in article.findall(".//MedlineCitation/Article/Abstract/AbstractText"):
        value = element_text(element)
        if value:
            label = (element.attrib.get("Label") or "").strip()
            abstract_parts.append(f"{label}: {value}" if label else value)
    abstract = "\n".join(abstract_parts)
    authors = []
    for author in article_node.findall(".//AuthorList/Author"):
        collective = element_text(author.find("CollectiveName"))
        name = " ".join(filter(None, (element_text(author.find("ForeName")), element_text(author.find("LastName")))))
        if collective or name:
            authors.append(collective or name)
    doi = None
    for identifier in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if identifier.attrib.get("IdType") == "doi":
            doi = element_text(identifier)
            break
    publication_types = [value for value in (
        element_text(item) for item in article_node.findall(".//PublicationTypeList/PublicationType")
    ) if value]
    lowered_types = {value.casefold() for value in publication_types}
    version_status = (
        "retraction-notice" if "retraction of publication" in lowered_types
        else "correction-notice" if "published erratum" in lowered_types
        else "final-publication"
    )
    return {
        "pmid": pmid,
        "title": element_text(article_node.find("ArticleTitle")),
        "authors": authors,
        "venue": element_text(article_node.find(".//Journal/Title")) or element_text(citation.find("MedlineJournalInfo/MedlineTA")),
        "publication_date": parsed_date(article_node.find(".//JournalIssue/PubDate")),
        "electronic_publication_date": parsed_date(article_node.find("ArticleDate")),
        "doi": doi,
        "pubmed_revision_date": parsed_revision_date(citation.find("DateRevised")),
        "publication_types": publication_types,
        "version_status": version_status,
        "abstract_sha256": hashlib.sha256(abstract.encode("utf-8")).hexdigest(),
        "abstract_character_count": len(abstract),
    }


def fetch_url(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
        return response.read()


def verify_refetched_sources(requests: list[dict], discoveries: list[dict]) -> list[str]:
    """Re-fetch omitted EFetch bodies and independently derive every canonical source field."""
    errors = []
    discovery_by_pmid = {record.get("identifiers", {}).get("pmid"): record for record in discoveries}
    for request_record in requests:
        if request_record.get("request_type") != "efetch":
            continue
        raw = fetch_url(request_record.get("request_url", ""))
        if hashlib.sha256(raw).hexdigest() != request_record.get("response_sha256"):
            errors.append("recent-review PubMed source revision")
        articles = [parse_source_article(article) for article in ET.fromstring(raw).findall("PubmedArticle")]
        if {article["pmid"] for article in articles} != set(request_record.get("requested_pmids", [])):
            errors.append("recent-review refetched PMID coverage")
        for source in articles:
            record = discovery_by_pmid.get(source["pmid"], {})
            expected = {
                "pmid": record.get("identifiers", {}).get("pmid"),
                "title": record.get("title"),
                "authors": record.get("authors"),
                "venue": record.get("venue"),
                "publication_date": record.get("publication_date"),
                "electronic_publication_date": record.get("electronic_publication_date"),
                "doi": record.get("identifiers", {}).get("doi"),
                "pubmed_revision_date": record.get("pubmed_revision_date"),
                "publication_types": record.get("provenance", {}).get("publication_types"),
                "version_status": record.get("version_status"),
                "abstract_sha256": record.get("abstract_sha256"),
                "abstract_character_count": record.get("abstract_character_count"),
            }
            if source != expected:
                errors.append("recent-review PubMed source-derived record")
    return sorted(set(errors))


def cache_path_is_safe(cache: Path) -> bool:
    try:
        relative = cache.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return True
    return bool(relative.parts) and relative.parts[0] == "generated"


def verify(path: Path = COLLECTION, cache: Path | None = None, refetch: bool = False) -> list[str]:
    errors = []
    try:
        manifest = yaml.safe_load((path / "manifest.yaml").read_text(encoding="utf-8"))["collection"]
        selection_document = yaml.safe_load(SELECTION.read_text(encoding="utf-8"))
        storage_document = yaml.safe_load(STORAGE.read_text(encoding="utf-8"))
        queries = selection_document["pubmed"]["query_families"]
        query_order = selection_document["pubmed"]["expected_query_ids"]
        collections = {}
        declared_paths = set()
        for name in ("searches", "discoveries", "requests"):
            spec = manifest["records"][name]
            artifact = (path / spec["path"]).resolve()
            if artifact.parent != path.resolve():
                errors.append("recent-review path escapes run directory")
                continue
            declared_paths.add(artifact)
            collections[name] = read_jsonl(artifact)
            if sha256(artifact) != spec.get("sha256") or len(collections[name]) != spec.get("count"):
                errors.append(f"recent-review file hash/count: {name}")
        if declared_paths != {item.resolve() for item in path.glob("*.jsonl")}:
            errors.append("undeclared recent-review JSONL")
        if manifest.get("base_protocol_sha256") != sha256(PROTOCOL):
            errors.append("recent-review protocol hash")
        if manifest.get("selection_amendment_sha256") != sha256(SELECTION) or manifest.get("selection_amendment_id") != selection_document["amendment"]["amendment_id"]:
            errors.append("recent-review selection amendment")
        if manifest.get("storage_amendment_sha256") != sha256(STORAGE) or manifest.get("storage_amendment_id") != storage_document["amendment"]["amendment_id"]:
            errors.append("recent-review storage amendment")
        if manifest.get("mode") != "discovery-with-transient-abstracts" or manifest.get("source") != "pubmed" or manifest.get("abstract_text_committed") is not False:
            errors.append("recent-review mode/source")
        if not manifest.get("source_acknowledgement") or not manifest.get("snapshot_notice"):
            errors.append("recent-review NLM notice")

        searches = collections.get("searches", [])
        discoveries = collections.get("discoveries", [])
        requests = collections.get("requests", [])
        schemas = [
            (searches, yaml.safe_load(SEARCH_SCHEMA.read_text(encoding="utf-8")), "searches"),
            (discoveries, yaml.safe_load(DISCOVERY_SCHEMA.read_text(encoding="utf-8")), "discoveries"),
            (requests, yaml.safe_load(REQUEST_SCHEMA.read_text(encoding="utf-8")), "requests"),
        ]
        for records, schema, label in schemas:
            for index, record in enumerate(records):
                errors.extend(validate_schema(record, schema, f"{label}[{index}]"))

        request_by_id = {record.get("id"): record for record in requests}
        if len(request_by_id) != len(requests):
            errors.append("duplicate recent-review request id")
        pmids_by_query = {}
        for query_id in query_order:
            request_record = request_by_id.get(f"esearch-{query_id}")
            if request_record is None or request_record.get("request_type") != "esearch" or request_record.get("response_body_stored") is not True:
                errors.append("recent-review ESearch request set")
                continue
            body = request_record.get("response_body", "")
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != request_record.get("response_sha256"):
                errors.append("recent-review ESearch response hash")
            result = json.loads(body)["esearchresult"]
            pmids = [str(value) for value in result.get("idlist", [])]
            if int(result.get("count", 0)) != len(pmids) or result.get("warninglist"):
                errors.append("recent-review ESearch completeness")
            pmids_by_query[query_id] = pmids
            parsed = urlparse(request_record.get("request_url", ""))
            parameters = parse_qs(parsed.query)
            endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if endpoint != ESEARCH or parameters.get("db") != ["pubmed"] or parameters.get("term") != [queries[query_id]] or parameters.get("retmode") != ["json"] or parameters.get("retmax") != ["9999"]:
                errors.append("recent-review ESearch literal")

        expected_pmids = sorted({pmid for values in pmids_by_query.values() for pmid in values}, key=int)
        efetches = [record for record in requests if record.get("request_type") == "efetch"]
        expected_batches = [expected_pmids[start:start + 200] for start in range(0, len(expected_pmids), 200)]
        if len(efetches) != len(expected_batches):
            errors.append("recent-review EFetch request count")
        for page, batch in enumerate(expected_batches):
            request_record = request_by_id.get(f"efetch-{page}")
            if request_record is None or request_record.get("requested_pmids") != batch or request_record.get("response_body_stored") is not False or request_record.get("response_body") is not None:
                errors.append("recent-review rights-safe EFetch record")
                continue
            parsed = urlparse(request_record.get("request_url", ""))
            parameters = parse_qs(parsed.query)
            endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if endpoint != EFETCH or parameters.get("db") != ["pubmed"] or parameters.get("id") != [",".join(batch)] or parameters.get("retmode") != ["xml"]:
                errors.append("recent-review EFetch literal")
            if not re.fullmatch(r"[0-9a-f]{64}", request_record.get("response_sha256", "")):
                errors.append("recent-review EFetch response hash")

        searches_by_query = {record.get("query_id"): record for record in searches}
        if set(searches_by_query) != set(query_order) or len(searches_by_query) != len(searches):
            errors.append("recent-review search set")
        storage_id = storage_document["amendment"]["amendment_id"]
        for query_id in query_order:
            search = searches_by_query.get(query_id, {})
            if search.get("protocol_id") != storage_id or search.get("query_or_endpoint") != queries[query_id] or search.get("result_count") != len(pmids_by_query.get(query_id, [])):
                errors.append("recent-review search provenance")
            if search.get("provenance", {}).get("ordered_pmids") != pmids_by_query.get(query_id, []):
                errors.append("recent-review ordered PMID trace")

        query_ids_by_pmid = defaultdict(list)
        for query_id in query_order:
            for pmid in pmids_by_query.get(query_id, []):
                query_ids_by_pmid[pmid].append(query_id)
        discovery_by_pmid = {record.get("identifiers", {}).get("pmid"): record for record in discoveries}
        if set(discovery_by_pmid) != set(expected_pmids) or len(discovery_by_pmid) != len(discoveries):
            errors.append("recent-review discovery coverage")
        for pmid in expected_pmids:
            record = discovery_by_pmid.get(pmid, {})
            expected_query_ids = query_ids_by_pmid[pmid]
            expected_search_ids = [searches_by_query[query_id]["id"] for query_id in expected_query_ids]
            if record.get("query_ids") != expected_query_ids or record.get("search_run_id") != expected_search_ids[0] or record.get("provenance", {}).get("search_run_ids") != expected_search_ids:
                errors.append("recent-review discovery query trace")
            if record.get("source_url") != f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" or record.get("version_status") != "final-publication":
                errors.append("recent-review PubMed source")
            if not isinstance(record.get("publication_date"), str) or record["publication_date"][:4] < "2021" or record["publication_date"][:4] > "2026":
                errors.append("recent-review publication window")
            if "abstract" in record or record.get("provenance", {}).get("abstract_text_committed") is not False:
                errors.append("recent-review committed abstract text")
            if not re.fullmatch(r"[0-9a-f]{64}", record.get("abstract_sha256", "")) or not isinstance(record.get("abstract_character_count"), int) or record.get("abstract_character_count") <= 0:
                errors.append("recent-review abstract identity")

        if manifest.get("query_hits") != sum(len(values) for values in pmids_by_query.values()) or manifest.get("unique_pmids") != len(expected_pmids) or manifest.get("abstracts_fetched") != len(discoveries):
            errors.append("recent-review manifest counts")
        if Counter(record.get("request_type") for record in requests) != Counter({"esearch": len(query_order), "efetch": len(expected_batches)}):
            errors.append("recent-review request counts")

        if cache is not None:
            if not cache_path_is_safe(cache):
                errors.append("recent-review unsafe abstract cache path")
                return sorted(set(errors))
            cache_records = read_jsonl(cache)
            cache_by_pmid = {record.get("pmid"): record for record in cache_records}
            if set(cache_by_pmid) != set(expected_pmids) or len(cache_by_pmid) != len(cache_records):
                errors.append("recent-review abstract cache coverage")
            for pmid in expected_pmids:
                cached = cache_by_pmid.get(pmid, {})
                record = discovery_by_pmid.get(pmid, {})
                abstract = cached.get("abstract", "")
                if hashlib.sha256(abstract.encode("utf-8")).hexdigest() != record.get("abstract_sha256") or len(abstract) != record.get("abstract_character_count"):
                    errors.append("recent-review abstract cache hash")
                if cached.get("abstract_sha256") != record.get("abstract_sha256") or cached.get("retrieved_at") != record.get("retrieved_at"):
                    errors.append("recent-review abstract cache identity")
                if cached.get("efetch_response_sha256") != record.get("provenance", {}).get("efetch_response_sha256"):
                    errors.append("recent-review abstract cache response trace")
        if refetch:
            errors.extend(verify_refetched_sources(requests, discoveries))
    except (KeyError, OSError, TypeError, ValueError, yaml.YAMLError, json.JSONDecodeError) as error:
        errors.append(f"load error: {error}")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=COLLECTION)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--refetch", action="store_true", help="re-fetch PubMed EFetch responses and verify source derivation")
    arguments = parser.parse_args()
    errors = verify(arguments.collection.resolve(), arguments.cache.resolve() if arguments.cache else None, arguments.refetch)
    if errors:
        print("FAILED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Recent serum/plasma review verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
