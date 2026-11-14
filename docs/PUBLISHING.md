# Publishing and review

## Public use

Manifest and range downloads are public and unauthenticated. Installing RiemannSearch, synchronizing public data, running local computations, saving results, and exporting JSON do not require a GitHub account or token.

## Optional contributor proposals

The in-app contribution path is disabled until maintainers register a GitHub App and deploy the optional service. When enabled, a contributor may use GitHub App device sign-in. The desktop sends the one-time GitHub user token only to the configured HTTPS service; the service validates the identity, discards that token, and returns a short-lived signed service session. The GitHub App private key and installation credential stay exclusively on the server.

The service validates the record, checks it begins at the current manifest's next required index, applies user/address rate limits, and creates a uniquely named branch and reviewable pull request. Its installation token is restricted to this repository and `contents:write` plus `pull_requests:write`. The service does not update `main`, merge PRs, or advance the global checkpoint. A maintainer must review result provenance, hashes, index sequence, and CI checks before accepting a record.

Contributors may also export a validated local record and submit it through the repository's normal pull-request workflow. Never include a local database, logs, notes, machine paths, credentials, or unreviewed experiments.

## Maintainer setup

1. Review the manifest, schemas, validator, and branch protections.
2. Protect `main` from force pushes and require review plus CI validation.
3. Keep workflow token permissions read-only by default; only Pages deployment requests Pages write permissions.
4. If enabling the optional service, register a GitHub App for this repository with only Contents and Pull requests write permissions, enable Device Flow, and configure App ID, client ID, installation ID, private key, and a 32-byte-or-longer signing key in the server secret store. Use persistent service storage for rate limits.
5. Set the desktop's optional service URL only after HTTPS and health/config checks pass. Public reads continue without it.
6. Review and merge genuine contiguous proposals through protected-branch review. A successful validator is structural evidence, not an independent mathematical recomputation.

The approved first-required index is `10,000,000,000,000`; the current checkpoint is `null` with no accepted ranges. Failed historical local database rows were not included.
