# Witnesses in the Margins — Gewita

[简体中文](README.md) · English

**Gewita** parses references, extracts citations, aligns quoted text with supplied sources, and checks bibliographic records against Crossref or arXiv when online verification is requested.

[![PyPI](https://img.shields.io/pypi/v/gewita)](https://pypi.org/project/gewita/)
[![Python](https://img.shields.io/pypi/pyversions/gewita)](https://pypi.org/project/gewita/)
[![CI](https://github.com/cloudydreamland/WitnessesInTheMargins/actions/workflows/ci.yml/badge.svg)](https://github.com/cloudydreamland/WitnessesInTheMargins/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
## Quick start

```bash
python -m pip install gewita
```

Or install from source (latest development version):

```bash
git clone https://github.com/cloudydreamland/WitnessesInTheMargins.git
cd WitnessesInTheMargins
python -m pip install .
```

Python API:

```python
from gewita import align_quote

source = "Attention can model long-range dependencies."
result = align_quote("model long-range dependencies", source)

if result.level == "VERBATIM":
    assert source[result.start:result.end] == "model long-range dependencies"
```

Online bibliographic lookup is opt-in:

```bash
gewita check paper.md --sources sources/ --online
```

## What it reports

- GB/T 7714, numbered, and limited APA-style reference parsing with unparsed entries retained.
- Citation extraction and quote alignment as `VERBATIM`, `NEAR`, `PARAPHRASE`, or `NOT_FOUND`.
- Exact source offsets for verbatim matches.
- Optional DOI, Crossref, and arXiv existence checks with bounded requests.
- Markdown/JSON reports and a local reference fingerprint store.

## Limits

`NOT_FOUND` means the text was not found in the supplied sources; it does not establish that a claim is false. Offline mode does not determine whether a publication exists. `PARAPHRASE` currently measures lexical overlap, not semantic entailment. Reference parsing is heuristic and reports incomplete entries rather than inventing fields. Online lookup depends on the queried services and their coverage.

## Documentation

- [简体中文](README.md)
- [Competitor and method notes](docs/competitors.md)
- [Evaluation results](benchmarks/results.md)
- [Changelog](CHANGELOG.md)
- [Roadmap](ROADMAP.md)

## Development and security

See [CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues privately; see [SECURITY.md](SECURITY.md).

## Feedback and contributing

Use [Discussions](https://github.com/cloudydreamland/WitnessesInTheMargins/discussions) for questions and ideas, and [Issues](https://github.com/cloudydreamland/WitnessesInTheMargins/issues) for reproducible bugs. Share only synthetic or redacted minimal examples; never upload personal data, API keys, or private source text. Report security issues privately as described in [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
