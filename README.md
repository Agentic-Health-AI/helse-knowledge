# Helse Knowledge

Open, traceable research corpora and evidence synthesis for agentic health products.

This public repository is deliberately separate from the Helse dashboard and all private health
data. It collects research under a frozen protocol, records screening and extraction, and only then
produces versioned syntheses and source-bound claims.

The first pilot is **serum/plasma 25-hydroxyvitamin D (25(OH)D)**.

- [Research Corpus Contract 0.1](docs/research-corpus-contract.md)
- [25(OH)D pilot](measurements/vitamin-d-25-oh/index.md)
- [Helse Evidence Profile extension](profile/helse-evidence-profile.yaml)
- [Pinned OKF 0.2](profile/okf-0.2-pin.yaml)
- [25(OH)D discovery collection](measurements/vitamin-d-25-oh/collection/2026-08-29/README.md)
- [Licensing](LICENSE.md)

Status: protocol 0.1.1 has collected and LLM-screened a PubMed meta-analysis corpus. Of 546 unique
records, 83 are included, 40 excluded and 423 await full text. Screening is not evidence, and no
medical claim is published. Run
`python3 scripts/verify_repository.py --root .` and
`python3 scripts/verify_discovery_collection.py` plus `python3 scripts/verify_screening.py` to verify
the contracts, collection and screening.
