# Recent serum/plasma review collection

Status: **collected discovery snapshot; not screened or extracted**

This is the first collection produced under frozen selection amendment 0.1.2 and rights-safe
storage amendment 0.1.3. The three literal PubMed queries were executed on 2026-08-30 Copenhagen
time with a frozen publication cutoff of 2026-08-29.

The run returned 46 query hits and 39 unique PMIDs:

| Publication year | Unique records |
| --- | ---: |
| 2021 | 6 |
| 2022 | 6 |
| 2023 | 8 |
| 2024 | 8 |
| 2025 | 4 |
| 2026 | 7 |

The 39 records are candidates, not included evidence. Some match more than one query, and title or
abstract screening may still exclude disease-specific, pregnancy-only, child-only or otherwise
out-of-scope reviews. No record in this directory supports a medical claim by itself.

## Abstract handling

PubMed EFetch returned an abstract for every PMID. Abstracts are the complete permitted processing
source for this method: the later parser may use only facts stated in the abstract, and missing or
conflicting values remain `unknown` or `unresolved`. Full text is neither required nor a fallback.

Raw abstract text and the abstract-bearing EFetch XML are not committed because redistribution
rights have not been established for every abstract. The collector writes the text to the ignored
local cache `generated/pubmed-recent-reviews/abstracts.jsonl`. Canonical discovery records instead
preserve the PMID, PubMed URL, retrieval time, text hash, character count, PubMed revision date and
EFetch response hash. Exact ESearch responses are committed because they contain search metadata
and identifiers rather than article abstracts.

This is a dated PubMed snapshot and may not reflect later NLM corrections or updates. PubMed data
is provided by the U.S. National Library of Medicine (NLM); NLM does not endorse this project.

## Files

- `manifest.yaml`: protocol identities, hashes and collection counts.
- `search-runs.jsonl`: literal queries, translations and ordered PMID results.
- `discoveries.jsonl`: deduplicated bibliographic records and abstract identities.
- `requests.jsonl`: reproducible request traces and safe raw responses.

## Verification

Verify the committed, rights-safe snapshot:

```sh
python3 scripts/verify_recent_serum_reviews.py
```

On the collecting machine, also prove that every cached abstract matches its canonical identity:

```sh
python3 scripts/verify_recent_serum_reviews.py \
  --cache generated/pubmed-recent-reviews/abstracts.jsonl
```

Verify the omitted EFetch body directly against the current PubMed source. This transiently
re-fetches the response, derives all canonical metadata and abstract hashes, and writes no source
text:

```sh
python3 scripts/verify_recent_serum_reviews.py \
  --cache generated/pubmed-recent-reviews/abstracts.jsonl \
  --refetch
```

The collector refuses to overwrite a collection or write an abstract cache inside this repository
outside the ignored `generated/` directory. A later append-only run must use a new output directory:

```sh
python3 scripts/collect_recent_serum_reviews.py \
  --output measurements/vitamin-d-25-oh/collection/NEW-RUN \
  --cache generated/pubmed-recent-reviews/NEW-RUN-abstracts.jsonl
```

The collection is discovery only. Screening, extraction, synthesis and claims are separate future
artifacts.
