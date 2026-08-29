# Helse Knowledge

Open, traceable research corpora and evidence synthesis for agentic health products.

This public repository is deliberately separate from the Helse dashboard and all private health
data. It collects research under a frozen protocol, records screening and extraction, and only then
produces versioned syntheses and source-bound claims.

The first pilot is **serum/plasma 25-hydroxyvitamin D (25(OH)D)**.

- [Research Corpus Contract 0.1](docs/research-corpus-contract.md)
- [Latest established review method 0.1](docs/latest-established-review-method.md)
- [25(OH)D pilot](measurements/vitamin-d-25-oh/index.md)
- [Helse Evidence Profile extension](profile/helse-evidence-profile.yaml)
- [Pinned OKF 0.2](profile/okf-0.2-pin.yaml)
- [25(OH)D discovery collection](measurements/vitamin-d-25-oh/collection/2026-08-29/README.md)
- [25(OH)D full-text availability](measurements/vitamin-d-25-oh/fulltext/2026-08-30/README.md)
- [Licensing](LICENSE.md)

Status: protocol 0.1.1 has collected and LLM-screened an over-broad PubMed calibration corpus. Of 546 unique
records, 83 are included, 40 excluded and 423 await full text. The 506 non-excluded records have a
source-bound PMC availability inventory; 236 are eligible for later Open Access retrieval. No full
text has been downloaded, screening is not evidence, and no medical claim is published. Run
`python3 scripts/verify_repository.py --root .` and
`python3 scripts/verify_discovery_collection.py`, `python3 scripts/verify_screening.py` and
`python3 scripts/verify_fulltext_availability.py` to verify every completed stage.
