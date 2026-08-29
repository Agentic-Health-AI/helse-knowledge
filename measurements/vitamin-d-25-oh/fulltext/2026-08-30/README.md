# Full-text availability inventory — 2026-08-30

This stage inventories the 506 non-excluded PubMed records after screening. It does not download
article text, extract evidence, synthesize results or publish claims.

The inventory contains 236 records in the PMC Open Access Subset, 40 records present in PMC without
confirmed reuse status and 230 records not found in PMC. The latter two groups fail closed. Only a
record with a PMCID and membership in the PMC Open Access Subset has
`extraction_allowed: true`.

`requests.jsonl` preserves the exact nine public NCBI JSON responses used by the collector, their
request URLs, timestamps and byte hashes. The verifier reconstructs every availability record from
those responses and the frozen screening corpus. It also checks 200-ID PMC ID Converter batches,
100-ID PubMed Open Access-filter batches, complete screening coverage and the fail-closed rule.

Reproduce into a fresh directory and verify it with:

```sh
python3 scripts/collect_fulltext_availability.py --output /tmp/helse-fulltext-reproduction
python3 scripts/verify_fulltext_availability.py --fulltext /tmp/helse-fulltext-reproduction
```

The PMC Open Access Subset is the mechanical retrieval gate, not permission to republish an article
or ignore its license. A later downloader must use an NCBI-approved automated retrieval service and
preserve the article-level license. This inventory itself contains only public metadata and API
responses.

Source contracts: [PMC ID Converter API](https://pmc.ncbi.nlm.nih.gov/tools/id-converter-api/) and
[PMC Open Access Subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/).
