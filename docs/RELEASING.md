# Repository release and publication procedure

This repository does not yet publish desktop binaries. This procedure covers public research data and the static progress dashboard.

## Before a research-data pull request

- Export only data approved for public release.
- Confirm each record follows the current repository schema.
- Verify record IDs, timestamps, index continuity, interval endpoints, backend, precision, and verification metadata.
- Confirm that no personal information, credential, private database, or local profile is included.
- Run the repository validator and both test suites.

## Review

A maintainer should review:
- Source provenance and reproducibility.
- Duplicate or overlapping indices.
- Any gaps in the proposed global sequence.
- Verification metadata and the limits of the validator.
- Whether the checkpoint advances monotonically.
- Whether the proposed public data is appropriate to disclose.

Do not accept a checkpoint advancement solely because JSON validation passes.

## Merge

- Require the validation workflow to pass.
- Merge through a pull request.
- Do not force-push or rewrite shared history.
- Record the accepted commit SHA in the maintainer's publication notes.

## Dashboard deployment

A qualifying push to `main` triggers the Pages workflow. Confirm the build and deployment run succeeds, then inspect the published site and its checkpoint state. The first Pages setup requires an owner to select GitHub Actions under repository Settings → Pages.

## Data corrections

Do not silently rewrite scientific records. Prefer an explicit correction record and a documented maintainer review. Preserve the audit trail and explain any correction to previously published metadata.

## Desktop application releases

The desktop application is not currently built or released from this repository. Do not upload an executable or claim a Store-ready release through this data-network workflow. Follow the desktop project's separate release, signing, licensing, and Microsoft Store procedures.
