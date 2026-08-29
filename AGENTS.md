# Helse Knowledge — agent instructions

This repository owns public research corpora, evidence extraction, synthesis and reusable claims.
It does not own the Helse dashboard or any user's data.

## Hard boundary

- Never access, copy, infer, generate or commit personal health data, identifiers, credentials,
  private clinical records or fixtures derived from them.
- Never copy material from the Helse application repository unless it is explicitly public,
  non-personal and required by this repository's contract.
- Do not republish copyrighted full text without compatible redistribution rights.

## Method

- Freeze and version a search protocol before collecting research.
- Keep discovery, screening, extraction, synthesis and claims as separate artifacts.
- Discovery is not evidence. Only included, source-bound extractions feed synthesis.
- Preserve provenance and unknown values; never invent metadata.
- LLMs parse and audit source-bound content under frozen prompts and schemas; deterministic reducers
  decide which audited fields may advance.
- Mark preprints clearly; they cannot alone support a stable conclusion.
- Record disagreements and uncertainty instead of forcing false consensus.
- There are no human approval gates. Unsupported, conflicting or incomplete evidence resolves to
  `unknown` or `unresolved`, never to an invented answer.

## Architecture

- Canonical knowledge is Markdown, JSONL and YAML.
- Generated databases, indexes, chunks and embeddings are disposable.
- Prefer deterministic scripts and small reviewable diffs.
- Pin the applicable OKF specification and keep Helse extensions in a versioned profile.
- Do not integrate with the Helse app until the corpus contract, D-vitamin pilot and ALAT
  portability test establish a stable read contract.
