# Latest established review method 0.1

Status: **frozen method**
Frozen: **2026-08-30**

## Purpose

Build a small, current and reproducible review corpus for one measurement without treating every
historical or disease-adjacent review as active evidence.

## Selection algorithm

1. Define the analyte, specimen, population, question and outcome before searching.
2. Search final-publication systematic reviews and meta-analyses indexed in PubMed and published in
   the most recent five calendar years through the frozen cutoff. Exclude preprints and protocols;
   do not infer peer-review status when PubMed does not state it.
3. Require an analyte-specific title signal and an explicit specimen signal in the title or
   abstract. A broad MeSH match alone is insufficient.
4. Require a PubMed abstract. The abstract is the complete source scope for this method; full text
   is not a collection or processing dependency.
5. Preserve the literal query, exact raw PubMed responses, abstracts, timestamps and hashes before
   screening.
6. Parse and audit only facts stated in the abstract. Missing or conflicting facts remain
   `unknown` or `unresolved`; they are not completed from model knowledge.
7. Within the same normalized question, population and outcome coverage, prefer the review with
   the latest reported literature-search end date. If that date is absent, use publication date as
   the fallback ordering field.
8. Retain overlapping older reviews for provenance, but do not count them as independent evidence
   when a newer review covers the same studies and question.
9. If no eligible review exists for a frozen question, extend the publication window backwards in
   five-year blocks. Stop after the first block that yields an eligible review. Do not search back
   by default merely to enlarge the corpus.

## Abstract sufficiency

An abstract may support only the fields it explicitly reports. Typical usable fields are review
design, population, number of studies or participants, exposure or intervention, comparator,
outcome, pooled estimate, uncertainty and stated limitations. Every accepted field retains an
exact abstract source span.

A review can feed a synthesis only when the abstract supports all fields required for that specific
claim. An incomplete abstract remains in discovery but contributes no invented values. No human or
full-text fallback is used by this method.

## D-vitamin pilot scope

For the serum/plasma 25(OH)D pilot, the current review corpus covers:

- measurement, assay and standardization;
- adult population distributions, reference context and reported thresholds; and
- dose-response or categorized associations with all-cause mortality, fractures and falls.

General supplementation reviews and disease-specific vitamin D reviews are outside this corpus
unless their abstract explicitly analyses outcomes by measured serum/plasma 25(OH)D level. Child,
adolescent and pregnancy-only populations are excluded from the adult pilot.

The 0.1.1 collection is retained as an over-broad calibration run. It is not silently rewritten or
used as the active corpus for this method.
