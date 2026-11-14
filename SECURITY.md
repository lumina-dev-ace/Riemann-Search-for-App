# Security policy

## Scope

This repository contains public research metadata, validation utilities, and a static website. The desktop application source and private user databases are not intended to be stored here.

## No credential required for public use

Public research browsing and checkpoint downloads are intended to work without a GitHub account or personal access token. A desktop user must never be asked to paste a GitHub token merely to install the application, synchronize public data, run a local experiment, or save local results.

The desktop executable must not contain a permanent GitHub credential, GitHub App private key, or server secret. Public reads should use unauthenticated HTTPS with sensible caching. Any future direct-publishing service must hold narrowly scoped GitHub App credentials server-side.

## Do not publish secrets or private data

Never put any of the following in an issue, pull request, commit, research record, workflow log, or website:

- GitHub tokens, passwords, private keys, or recovery codes.
- Private database files, local application profiles, or unreviewed experiment exports.
- Personal email addresses, home addresses, account identifiers, or other private contributor information.
- Diagnostic logs before checking and redacting them.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use the repository's **Security** tab and **Report a vulnerability** option if private vulnerability reporting is enabled. If that option is unavailable, contact the repository maintainer through a private channel already known to you and provide only the minimum details needed to reproduce the issue.

Do not attach sensitive files to public issues.

## Maintainer response

The maintainer should acknowledge a private report, assess impact, prepare a fix, and coordinate disclosure after a patched version or mitigation is available. Do not publish exploit details while a vulnerability is unresolved.

## Research-data integrity

A validator pass is a structural check, not an independent mathematical recomputation. Suspected fabricated, altered, or incorrectly described research data should be reported privately to the maintainer for review; do not present finite numerical verification as a proof of the Riemann Hypothesis.
