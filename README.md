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
- [Human decision register](docs/human-decision-register.md)
- [25(OH)D corpus manifest](measurements/vitamin-d-25-oh/corpus-manifest.yaml)
- [Licensing](LICENSE.md)

Status: 0.1 implementation fixtures only. Synthetic aggregate-only records exercise the contract;
all searches are `never-run`, real collection remains blocked, and no medical claim is published.
Run `python3 scripts/verify_repository.py --root .` to verify the canonical bundle.
