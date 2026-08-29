---
type: Research Protocol
status: proposed-for-freeze
---

# 25(OH)D research protocol

Version 0.1.0 is a canonical specification, not an executed search. `collection_allowed: false` in
the companion YAML is authoritative. It may change to `frozen` only after a real human approval
event; no such event is recorded here.

It covers adults in defined population strata and settings, separately tagged special populations,
and six question families: measurement, distribution, associations, interventions, harms, and
disagreement. The pilot outcomes are fractures, falls, all-cause mortality, hypercalcemia,
nephrolithiasis, and renal adverse events. It does not assume findings transfer to special
populations.

PubMed and medRxiv search specifications remain `never-run`. The YAML freezes seven field-tagged
PubMed query families with a 2026-08-29 cutoff and a date-complete medRxiv API crawl followed by a
local analyte regex. Exact execution, pagination, eligibility, screening, relation, extraction,
risk-of-bias and structured narrative-synthesis rules are in [protocol.yaml](protocol.yaml).

The four choices that still require actual human approval are isolated in the
[decision register](../../docs/human-decision-register.md). No collection may start before all four
are approved and the protocol status is changed through a real human approval event.
