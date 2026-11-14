# RiemannSearch Global Research Network

[![Research validation](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/validate.yml)
[![CodeQL](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/lumina-dev-ace/Riemann-Search-for-App/actions/workflows/codeql.yml)

This public repository is the single source of shared RiemannSearch progress. The desktop application performs numerical computation and keeps local research in each user's database. Public synchronization is read-only and works without a GitHub account or token.

## Current approved boundary

- First required zero index: `10,000,000,000,000`.
- Global completed checkpoint: `null`.
- Accepted ranges: `0`.

The first required index is a boundary, not a computed result. No global progress is claimed until valid, consecutive, Arb-rechecked result records are accepted by maintainers. Failed historical local rows were not imported.

## Canonical layout

- `data/global_manifest.json`: authoritative checkpoint and range references.
- `data/ranges/`: immutable accepted result records.
- `data/schema/`: versioned manifest and result schemas.
- `progress/`: static view of the manifest and referenced records.
- `research_network.py`: public read, validation, and export functions used by the optional service.
- `services/contribution_api/`: optional GitHub App proposal service; disabled until maintainers configure and deploy it.
- `tools/` and `tests/`: repository validation and bounded regression checks.

The obsolete `global/`, `records/`, `schemas/`, `riemann_network/`, and `website/` formats are removed from this migration branch. Do not reintroduce a competing checkpoint representation.

## Local validation

Python 3.10 or later is required for the standard-library validator and reader tests. Optional contribution-service tests require the pinned dependencies in `services/contribution_api/requirements-test.txt`.

```powershell
python -m pip install -r services/contribution_api/requirements-test.txt
python -m compileall -q tools research_network.py services
python tools/validate_research_repository.py
python -m unittest discover -s tests -p "test_*.py" -v
python tools/validate_website.py
node --check progress/app.js
```

The Pages workflow publishes after a maintainer-approved change reaches `main`; it has explicit deployment permissions and can also be run manually.

## Access and contributions

Anyone can install and use the desktop app, synchronize public data, compute locally, save results, and export JSON without a GitHub account. In-app submissions are optional: a configured GitHub App service authenticates contributors, validates submissions, and opens reviewable pull requests. The service keeps its private key on the server and cannot merge a proposal or advance the checkpoint. Maintainers review and accept a consecutive range through repository review and CI. See [publishing](docs/PUBLISHING.md), [contributing](docs/CONTRIBUTING.md), and [security](SECURITY.md).

## Scientific integrity

Repository validation checks the declared schema, integrity hashes, result/index association, metadata, and consecutive coverage. It does not recompute a zero or establish a theorem. A numerical approximation or finite interval recheck is not a proof of the Riemann Hypothesis.

## License

No software or research-data license has been selected. See [LICENSE-STATUS.md](LICENSE-STATUS.md); public visibility does not grant reuse rights.
