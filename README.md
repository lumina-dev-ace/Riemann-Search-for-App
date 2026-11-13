# RiemannSearch Research Network

A public, local-first research-data network for the RiemannSearch desktop application.

**Current network status: awaiting initialization.** No global checkpoint has been declared. The first checkpoint must be derived from actual, independently validated, contiguous research records—not guessed or copied from a local high-water mark.

## Repository map

- `global/checkpoint.json` — authoritative public checkpoint metadata.
- `records/` — immutable, versioned research-record exports.
- `schemas/` — JSON Schemas for records and checkpoint metadata.
- `tools/` — standard-library validator and tests.
- `website/` — static GitHub Pages progress dashboard.
- `.github/workflows/` — validation and Pages deployment workflows.
- `docs/` — integration, contribution, and trust-model documentation.

## Trust and scientific scope

The global checkpoint means the highest index for which every preceding index is represented by valid, contiguous, Arb-interval-verified records accepted into the repository. Candidate counts and locally attempted ranges are not global progress.

A passing repository validator checks data shape, sequence continuity, and declared verification metadata. It does not recompute the Riemann zeta function and is not a mathematical proof. Finite numerical verification—however extensive—does not prove the Riemann Hypothesis.

## Start here

1. Read [the data contract](docs/DATA_FORMAT.md) and [desktop integration guide](docs/INTEGRATION.md).
2. Export records using the schemas in `schemas/`.
3. Run `python tools/validate_network.py` (Python 3.10+; standard library only).
4. Submit reviewed data through a pull request.

## Publishing safety

The desktop app must persist locally before any network action. Publishing must be an explicit, authenticated operation with serialized, compare-and-swap checkpoint updates. No permanent personal access token or private key may be embedded in the desktop executable. Until a secure publishing service and contributor identity policy exist, use pull requests.

## License

No software or dataset license has been selected yet. See [LICENSE-STATUS.md](LICENSE-STATUS.md). Public visibility alone is not a reuse license.
