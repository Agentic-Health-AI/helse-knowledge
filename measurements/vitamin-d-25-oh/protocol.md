---
type: Research Protocol
status: frozen
---

# 25(OH)D research protocol

Version 0.1.0 is a frozen canonical specification, not an executed search. Git versions the exact
protocol and schemas; collection is permitted only while the repository verifier and tests pass.

The active pilot search scope is the append-only
[0.1.1 meta-analysis amendment](amendments/0.1.1-meta-analysis-pilot.yaml). It requires explicit
25(OH)D terms, collects PubMed meta-analyses only, derives disagreement from the included q1-q5
records, and defers the date-only medRxiv crawl.

It covers adults in defined population strata and settings, separately tagged special populations,
and six question families: measurement, distribution, associations, interventions, harms, and
disagreement. The pilot outcomes are fractures, falls, all-cause mortality, hypercalcemia,
nephrolithiasis, and renal adverse events. It does not assume findings transfer to special
populations.

The base PubMed and medRxiv search specifications remain `never-run`. The amendment freezes six
narrow PubMed query families with a 2026-08-29 cutoff. Exact eligibility, screening, relation,
extraction, risk-of-bias and structured narrative-synthesis rules remain in
[protocol.yaml](protocol.yaml).

Semantic processing uses a source-bound LLM parser, an independent LLM audit and deterministic
reduction. Unsupported or conflicting evidence remains unresolved; there is no human approval or
fallback gate.
