# Desktop application integration

This repository defines the public data contract, validator, and static website. The actual RiemannSearch desktop source is not currently present here, so this commit cannot yet modify its application code or add working app-side network integration.

## Reading the network

The app may read `global/checkpoint.json` for the published checkpoint and `records/*.json` for immutable record exports. Use HTTPS and a configurable repository URL. Treat missing, stale, or malformed network data as unavailable; it must never interrupt local computation or local persistence.

## Publishing workflow

Publishing must be a separate, explicit action after local persistence:
1. Export the exact contiguous sequence from the latest global checkpoint + 1 through the proposed end index.
2. Confirm every index exists exactly once and that all entries intended for checkpoint advancement are Arb-interval verified.
3. Fetch the latest checkpoint immediately before publishing.
4. Reject proposals that overlap, skip indices, or fail to extend the current global checkpoint.
5. Submit the record and checkpoint proposal for maintainer review.
6. After acceptance, re-read the repository and store the resulting commit SHA locally.

A client-side read-then-write flow is not race-safe. Direct publishing requires a trusted server-side transaction or a carefully serialized compare-and-swap update. Never force-push. Never embed a permanent personal access token, GitHub App private key, or other secret in the desktop executable.

## Local-first guarantees

- Save numerical results and experiment state locally first.
- Offline or rejected publication leaves local data unchanged.
- The global checkpoint never decreases.
- Keep rejected exports available for review and retry.
- Candidate rows, attempted ranges, and a high-water setting are not completed consecutive zeros.
