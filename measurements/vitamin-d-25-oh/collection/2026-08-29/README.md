# PubMed meta-analysis discovery — 2026-08-29

This is the executed discovery stage for protocol amendment 0.1.1. Six literal PubMed queries
returned 910 query-result records representing 546 unique PMIDs:

| Query | Results |
| --- | ---: |
| q1-measurement | 283 |
| q2-distribution | 284 |
| q3-association | 64 |
| q4-intervention | 68 |
| q5-high-measured-level | 72 |
| q5-supplementation-harm | 139 |

The repeated records preserve query-level discovery provenance. Shared PMIDs are deduplicated only
in the next stage. `discoveries.jsonl` contains public bibliographic metadata, not abstracts or full
text. Every ESearch and EFetch response is represented by a timestamp and SHA-256 in
`search-runs.jsonl`; the manifest hashes both canonical JSONL files.

These records are unscreened discovery, not evidence. They cannot support a synthesis or claim.
Verify them with:

```sh
python3 scripts/verify_discovery_collection.py
```
