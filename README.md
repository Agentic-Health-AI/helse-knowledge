# Helse Knowledge

Open, traceable research corpora and evidence synthesis for agentic health products.

This public repository is deliberately separate from the Helse dashboard and all private health
data. It collects research under a frozen protocol, records screening and extraction, and only then
produces versioned syntheses and source-bound claims.

The first pilot is **serum/plasma 25-hydroxyvitamin D (25(OH)D)**.

- [Research Corpus Contract 0.1](docs/research-corpus-contract.md)
- [Latest established review method 0.2](docs/latest-established-review-method-0.2.md)
- [25(OH)D pilot](measurements/vitamin-d-25-oh/index.md)
- [Helse Evidence Profile extension](profile/helse-evidence-profile.yaml)
- [Pinned OKF 0.2](profile/okf-0.2-pin.yaml)
- [25(OH)D discovery collection](measurements/vitamin-d-25-oh/collection/2026-08-29/README.md)
- [25(OH)D full-text availability](measurements/vitamin-d-25-oh/fulltext/2026-08-30/README.md)
- [Current 25(OH)D review collection](measurements/vitamin-d-25-oh/collection/2026-08-30-recent-reviews/README.md)
- [Licensing](LICENSE.md)

Status: the active 0.1.3 method has collected 39 unique PubMed review candidates from 2021–2026 and
fetched an abstract for each into a rights-safe local cache. Canonical records contain reproducible
source identities and hashes, not raw abstract text. The older 0.1.1 corpus remains an over-broad
calibration run. Nothing in either corpus has been extracted into evidence or synthesized into a
medical claim. Run `python3 scripts/verify_repository.py --root .` and the stage verifiers in
`scripts/`, including `python3 scripts/verify_recent_serum_reviews.py`, to verify completed work.
