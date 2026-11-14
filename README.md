# RiemannSearch Research Network

[![Research data validation](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/validate.yml)
[![CodeQL](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/codeql.yml)

A public research-data repository and static progress dashboard for RiemannSearch. The desktop application performs local numerical work; this repository is intended to hold reviewed, shareable research records and public progress metadata.

## Current status

- **Global verified checkpoint:** not initialized.
- **Accepted research records:** none.
- **First required index in the current desktop project:** 10,000,000,000,000.
- **Completed research:** none is implied by that starting boundary.

The approved first-required index is a boundary, not a computed result. The global checkpoint must remain uninitialized until genuine, contiguous, verified research records have been reviewed and accepted.

> **Integration status:** this repository currently contains an initial checkpoint-and-record data contract. The final desktop implementation described in the project handoff uses a manifest-and-range contract under `data/global_manifest.json` and `data/ranges/`. These formats must be reconciled before the desktop application is allowed to publish or treat this repository as its authoritative network. Do not publish research using two competing formats.

## Repository layout

| Path | Purpose |
| --- | --- |
| `global/` | Initial checkpoint metadata scaffold |
| `records/` | Initial record storage scaffold |
| `schemas/` | Versioned JSON contracts for the current scaffold |
| `riemann_network/` | Read-only Python client for the current scaffold |
| `tools/` | Data and website validation plus dashboard-data generation |
| `website/` | Static public progress dashboard |
| `.github/workflows/` | CI, security analysis, and Pages deployment |
| `docs/` | Architecture, integration, data-format, and repository-operation guidance |

See [Architecture](docs/ARCHITECTURE.md) for the data flow and [Repository setup](docs/REPOSITORY_SETUP.md) for the one-time GitHub settings.

## Local validation

Python 3.10 or later is required. The validator and tests use the Python standard library.

```bash
python -m compileall -q tools riemann_network
python tools/validate_network.py
python -m unittest discover -s tools -p "test_*.py" -v
python -m unittest riemann_network.test_client -v
python tools/build_site_data.py
python tools/validate_site.py
node --check website/app.js
```

To preview the website locally:

```bash
python -m http.server 8000 --directory website
```

Then open `http://localhost:8000`. Do not open the HTML file directly because the page fetches its JSON data.

## Research integrity

The repository validator checks data shape, unique and contiguous indices, interval ordering, declared FLINT/Arb verification metadata, and checkpoint consistency. It does not independently recompute the zeta function or establish that a contributor's declared computation is correct. Review and reproducibility remain necessary.

Finite numerical verification, regardless of scale or precision, is not a proof of the Riemann Hypothesis.

## Public access and contributions

Browsing published research and downloading the public checkpoint are intended to require no GitHub account or personal access token. Submissions are separate from normal application use and are currently expected through reviewed pull requests.

The final desktop application must not require ordinary users to configure GitHub credentials. Any future direct-publishing service must keep its GitHub App private key and installation credentials server-side. See [Integration](docs/INTEGRATION.md) and [Security](SECURITY.md).

## Contribution and support

Read [Contributing](docs/CONTRIBUTING.md) before submitting changes. Use the issue forms for reproducible bugs or data-contract questions. For security reports, follow [Security](SECURITY.md).

## Licensing

No software or research-data license has been selected yet. See [LICENSE-STATUS.md](LICENSE-STATUS.md). Public visibility does not automatically grant reuse or redistribution rights.
