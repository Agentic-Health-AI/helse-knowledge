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

Status: protocol 0.1.1 has collected a PubMed meta-analysis discovery corpus. The 546 unique PubMed
records are unscreened discovery, not evidence, and no medical claim is published. Run
`python3 scripts/verify_repository.py --root .` and
`python3 scripts/verify_discovery_collection.py` to verify the contracts and collection.
