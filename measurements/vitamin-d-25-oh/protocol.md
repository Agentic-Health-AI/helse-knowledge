---
type: Research Protocol
status: frozen
---

# 25(OH)D research protocol

Version 0.1.0 is a frozen canonical specification, not an executed search. Git versions the exact
protocol and schemas; collection is permitted only while the repository verifier and tests pass.

It covers adults in defined population strata and settings, separately tagged special populations,
and six question families: measurement, distribution, associations, interventions, harms, and
disagreement. The pilot outcomes are fractures, falls, all-cause mortality, hypercalcemia,
nephrolithiasis, and renal adverse events. It does not assume findings transfer to special
populations.

PubMed and medRxiv search specifications remain `never-run`. The YAML freezes seven field-tagged
PubMed query families with a 2026-08-29 cutoff and a date-complete medRxiv API crawl followed by a
local analyte regex. Exact execution, pagination, eligibility, screening, relation, extraction,
risk-of-bias and structured narrative-synthesis rules are in [protocol.yaml](protocol.yaml).

Semantic processing uses a source-bound LLM parser, an independent LLM audit and deterministic
reduction. Unsupported or conflicting evidence remains unresolved; there is no human approval or
fallback gate.
