# Latest established review method 0.2

Status: **frozen method**
Frozen: **2026-08-30**

This method inherits the selection algorithm and abstract-sufficiency rules from version 0.1. It
changes only how PubMed abstract material is stored.

## Rights-safe abstract handling

- PubMed abstracts are sufficient processing sources for this method.
- Fetch the abstract through the official PubMed API into an ignored, disposable local cache.
- Give the parser and auditor the exact fetched text during their run.
- Canonical records preserve the PMID, PubMed URL, retrieval timestamp, abstract SHA-256, abstract
  character count, PubMed revision date when reported and processing provenance.
- Do not commit raw abstract text or abstract-bearing EFetch responses unless the record has a
  separately verified redistribution license.
- A later fetch must match the canonical abstract hash. A mismatch is a source revision and requires
  a new append-only collection run; it must not silently replace the earlier source identity.
- Preserve exact raw ESearch responses because they contain search metadata and identifiers, not
  article abstracts.
- Clearly acknowledge NLM as the PubMed data source and state that the collection is a dated
  snapshot that may not reflect the latest PubMed data.

Missing or conflicting abstract fields still resolve to `unknown` or `unresolved`. This storage
rule does not introduce full-text collection, a human gate or permission to reconstruct missing
content.

Official basis:

- <https://www.nlm.nih.gov/databases/download.html>
- <https://www.ncbi.nlm.nih.gov/home/about/policies/>
