# Desktop application integration

This repository currently includes an initial credential-free read client in `riemann_network/`, a preliminary checkpoint/record contract, a structural validator, and a static dashboard.

**Important:** the final desktop application handoff describes a different canonical format based on `data/global_manifest.json`, `data/ranges/`, `data/schema/`, and `progress/`. The current repository's `global/checkpoint.json` and `records/` format is not interchangeable. The desktop integration phase must reconcile the formats before using this repository as the authoritative research network. Do not publish real app-generated data through both formats.

## Intended public access

Public browsing and downloading research data are intended to work without a GitHub account, personal access token, or other user credential. The desktop app should fetch public data over HTTPS and use bounded caching. It should clearly indicate current, cached, stale, and unavailable states.

The current Python client reads only the preliminary checkpoint/record format in this repository. It is not yet proof that the final desktop application's manifest/range integration is connected.

## Local-first behavior

- Save numerical results and experiment state locally first.
- Network availability must never block computation or local persistence.
- Offline or rejected publication must leave local data unchanged.
- Keep cached public data visibly marked as stale when a refresh fails.
- Candidate rows, attempted ranges, and a high-water setting are not completed verified results.

## Contributions and publishing

The current public read client intentionally has no write method. Contributions should be submitted through reviewed pull requests.

Ordinary application users must never be required to configure a GitHub personal access token. Do not embed permanent repository credentials, GitHub App private keys, or server secrets in the desktop executable.

If direct in-app publishing is introduced later, use a trusted server-side contribution service with narrowly scoped GitHub App credentials held only on the server. Apply authentication, rate limiting, validation, human review, and concurrency-safe checkpoint updates. Do not permit anonymous clients to write directly to the main branch.

## Research boundary and scientific limits

The approved first required index in the desktop project is 10,000,000,000,000. That is a configured boundary, not a computed result. The completed global checkpoint remains uninitialized until genuine contiguous research records have been accepted.

Repository validation checks structure and declared metadata. It does not independently recompute the zeta function. Finite numerical verification is not a proof of the Riemann Hypothesis.
