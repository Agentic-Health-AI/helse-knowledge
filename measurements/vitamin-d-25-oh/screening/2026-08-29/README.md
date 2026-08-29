# LLM screening — 2026-08-29

This stage deduplicates the 910 PubMed query results to 546 unique PMIDs and screens each canonical
record under protocol amendment 0.1.1.

| Decision | Records |
| --- | ---: |
| included | 83 |
| excluded | 40 |
| awaiting-full-text | 423 |

A `gpt-5.6-luna` parser evaluated eight eligibility facts from PubMed publication types, title and
abstract locations. A separate call audited every fact. The deterministic `screening-reducer/0.1`
accepted only facts labelled `supported`; unsupported, conflicting or unknown facts became null.
The runner used 28 batches of at most 20 records with native response schemas requiring every
canonical record ID and valid per-record source locations.

The committed events contain facts, audit outcomes, source-location hashes, prompt/model/input/output
provenance and reducer inputs. They do not contain abstracts or full text. The ignored processing
cache is disposable.

Screening is not evidence. Included records cannot support synthesis or claims until lawful full
text is obtained and source-bound extraction is complete. Verify this stage with:

```sh
python3 scripts/verify_screening.py
```
