# Research Corpus Contract 0.1

Status: **0.1 pilot implementation — proposed for freeze**
Pilot: **serum/plasma 25-hydroxyvitamin D (25(OH)D)**  
Updated: **2026-08-29**

## Purpose

Helse Knowledge builds conclusions after collecting evidence, not before. It keeps each stage
independently inspectable and reproducible:

```text
frozen search protocol
        ↓
discovered research corpus
        ↓
screened research corpus
        ↓
source-bound extraction
        ↓
evidence synthesis
        ↓
published claims
```

Discovery is not evidence. Extraction is not synthesis. A published claim must be traceable through
all preceding stages.

This implementation is a synthetic, mechanically verified fixture; it is not human-approved and it
does not authorize collection. The **immutable collection baseline** is a specific frozen protocol
version plus its append-only amendments. It governs a collection run. **Profile stability** is a
later portability judgement: profile 0.1 becomes stable only after this pilot and a small ALAT pilot
fit without schema changes. Freezing a collection baseline does not imply profile stability.

## Repository boundary

This repository is public reference knowledge. It must never contain personal measurements, health
exports, names, identifiers, credentials, private clinical records, or fixtures derived from them.

Full copyrighted articles are included only when redistribution is permitted. Otherwise, preserve
durable identifiers, bibliographic metadata, links and original structured extractions.

Canonical knowledge lives in Markdown, JSONL and YAML. Databases, indexes, chunks and embeddings are
derived artifacts that must be safe to delete and rebuild.

## Contract layers

1. **OKF 0.2** supplies portable concepts, provenance and verification events.
2. **Helse Evidence Profile 0.1** supplies versioned research and medical semantics.
3. **Measurement islands** implement the profile for one normalized measurement.

The exact upstream pin is canonical in `profile/okf-0.2-pin.yaml`; the extension-only profile
references that pin. An upstream change requires an explicit profile migration.

## Stage A — protocol

The protocol is versioned before collection. A protocol marked `proposed-for-freeze` is a
specification only; it may become `frozen` only after a real human approval event. A frozen version
is immutable: later changes are append-only amendments with a reason and a new version. It records:

- normalized analyte, specimens and synonyms;
- separate research questions;
- populations and settings;
- interventions, comparators and outcomes where applicable;
- eligible study designs per question;
- sources, exact queries, date ranges and search date;
- language and full-text handling;
- inclusion and exclusion criteria;
- preprint, correction and retraction handling;
- deduplication and preprint-to-publication matching;
- screening and disagreement procedure;
- extraction fields, risk-of-bias method and synthesis plan.

A later change is a dated amendment with a reason. It does not silently rewrite the original search.

## Stage B — discovered corpus

The discovered corpus records everything returned by a documented search. Each record carries, when
available:

- stable local ID and durable external IDs such as PMID, DOI or medRxiv ID;
- title, authors, venue and publication date;
- source database, source URL, search run and query;
- retrieval time and content hash for preserved material;
- peer-review and version status;
- relations to duplicates, preprints, final publications, corrections and retractions;
- provenance for machine-populated metadata.

Unknown metadata remains unknown. It is never invented. A discovered record cannot support a
synthesis or claim.

## Stage C — screening

Screening uses explicit states:

```text
discovered → screening → included
                       ↘ excluded
                       ↘ awaiting-full-text
discovered → duplicate
included   → superseded-by-publication
included   → retracted
```

Every exclusion has a controlled reason and review event. A preprint and final publication are
linked and cannot be counted as independent studies. Retractions remain in the audit history but
cannot support active claims.

## Stage D — extraction

Each included study receives a source-bound extraction appropriate to its question:

- study design and preregistration;
- population, setting and sample size;
- specimen, analyte, assay, unit and calibration;
- intervention, comparator and exposure;
- outcome, follow-up and analysis population;
- estimate, uncertainty and model adjustments;
- missing data, attrition and material confounders;
- funding and declared conflicts when reported;
- limitations and risk-of-bias assessment;
- exact source locations;
- generator and verification events.

A machine may propose an extraction. Only an actual human review may add a `human:` verification
event. Source statements, reviewer assessments and interpretations remain separate.

## Stage E — synthesis

Synthesis uses only included, extracted evidence. It records:

- question, population and applicability;
- corpus and search cutoff;
- method;
- best-supported current conclusion;
- certainty and rationale;
- heterogeneity and material disagreement;
- limitations and unresolved questions;
- emerging evidence that is not yet sufficient to change the conclusion;
- claims created, changed or deprecated.

“Newest” means the best current synthesis after considering recency, design, quality, directness,
precision and consistency. The latest paper does not automatically win.

## Stage F — claims

Claims are small, source-bound statements usable by Helse. Numeric claims require enough context to
interpret them, including analyte, specimen, unit, applicable method, population, outcome and time
horizon where relevant.

The profile distinguishes at least:

- statistical reference interval;
- clinical decision threshold;
- outcome association;
- intervention effect;
- measurement or assay claim;
- safety or harm claim;
- authority recommendation as practice context;
- uncertainty or documented disagreement.

Preprints are visibly marked. They may appear in a research-frontier view, but cannot alone make a
synthesis or user-facing status stable.

## D-vitamin pilot questions

1. How is serum/plasma 25(OH)D measured, standardized and converted?
2. How do distributions vary by relevant population, season and setting?
3. Which measured levels are associated with specified outcomes?
4. What do randomized supplementation studies show for those outcomes?
5. What harms are associated with high measured levels or supplementation?
6. Where do high-quality studies disagree, and what explains the disagreement?

PubMed is the primary discovery backbone. medRxiv is a separately labelled frontier source.
Citation chaining may supplement a documented search but cannot replace it. Authorities and
guidelines are practice context, not automatically superior evidence.

## Roles

- Protocol owner approves questions, criteria and amendments.
- Collector runs searches and imports metadata without making conclusions.
- Screener applies inclusion rules and records reasons.
- Extractor produces source-bound structured observations.
- Synthesizer evaluates included evidence and proposes conclusions.
- Reviewer verifies interpretation and approves stable claims.
- Automation validates structure, provenance, links, states and reproducibility.

One person may hold several roles, but actions retain their role and provenance. Material uncertainty
is recorded or escalated once; there are no adversarial-review loops.

## Mechanical gates

Verification must fail when:

- a record cannot be traced to its search or source;
- an exclusion has no reason;
- an included study has no screening decision;
- a claim cites missing evidence or synthesis;
- a numeric claim lacks analyte, specimen, unit, method, population, outcome, time horizon or
  applicability where required;
- a retracted source supports an active claim;
- a preprint is represented as peer-reviewed;
- a stable conclusion is supported only by preprints;
- a machine proposal claims human verification;
- generated artifacts are required to rebuild canonical knowledge;
- personal or private health data or structured credentials are detected.

The manifest- and schema-driven local verifier also rejects duplicate IDs, undeclared JSONL,
missing source/query traces, invalid state transitions, broken relations and events, extraction
from non-included records, preprint/final double-counting, and canonical references to generated
artifacts. It validates contract mechanics, not medical correctness or human approval.

## Pilot sequence

1. Freeze this contract and the initial 25(OH)D protocol.
2. Define schemas and verify them against a synthetic corpus.
3. Collect PubMed and medRxiv results without synthesizing.
4. Screen and link duplicates, versions, corrections and retractions.
5. Extract included evidence.
6. Produce the first versioned synthesis and claims.
7. Build a read-only artifact for a future Helse knowledge plugin.
8. Model a small ALAT corpus with the same profile.
9. Fix demonstrated contract defects and freeze profile 0.1.

## Non-goals for 0.1

- personalized diagnosis or treatment;
- declaring one optimal vitamin D level for everyone;
- databases as canonical storage;
- embeddings before a measured retrieval need;
- autonomous publication of machine conclusions;
- mirroring copyrighted literature;
- expanding to all biomarkers before the ALAT portability test.
