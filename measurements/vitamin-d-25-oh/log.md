# Change log

## 2026-08-29

- Created the empty 25(OH)D pilot.
- Collection is blocked until the protocol is frozen.
- Added 0.1 proposed-for-freeze protocol, schemas, synthetic aggregate-only fixtures and local
  mechanical verification. No human approval, collection, medical synthesis or medical claim occurred.
- Froze amendment 0.1.1 to replace the overly broad primary-study preflight with six explicit
  25(OH)D meta-analysis queries. Q6 is derived, medRxiv is deferred, and no research was collected
  before the amendment.
- Replaced human approval gates with a Git-versioned LLM parse–audit–reduce contract. Ambiguous or
  unsupported evidence now remains unresolved; no research was collected by this change.
- Executed all six 0.1.1 PubMed queries and collected 910 query-result records representing 546
  unique PMIDs. The collection contains public bibliographic metadata only and remains unscreened.
  No synthesis or claim was produced.
- Parsed and independently audited all 546 unique records with source-bound `gpt-5.6-luna` batches,
  then applied screening-reducer 0.1. The result is 83 included, 40 excluded and 423
  awaiting-full-text records plus 364 exact-PMID duplicate relations. No extraction, synthesis or
  claim was produced.

## 2026-08-30

- Inventoried PMC and PMC Open Access Subset availability for all 506 non-excluded screening
  records. Exact public API responses are preserved so the verifier can reconstruct every status.
  The result is 236 Open Access retrieval candidates, 40 PMC records without confirmed reuse status
  and 230 records not found in PMC. No full text was downloaded and no extraction, synthesis or
  claim was produced.
