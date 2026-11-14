# Security policy

## Scope

This repository contains public research metadata, validation utilities, a static progress site, and optional contribution-service source. Private user databases and local profiles must not be committed.

## No credential required for public use

Public synchronization, local computation, saving, and export work without GitHub authentication. The desktop must not contain a PAT, GitHub App private key, installation token, or service signing secret. Optional contributor sign-in is only for proposal submission. App private keys and installation credentials belong in the trusted service's secret store.

## Proposal boundary

The service may validate submissions and create a reviewable branch/PR. It must not merge proposals or directly modify the default branch. Enforce rate limits, exact repository and permissions, stale-base checks, schema/hash/consecutive-index validation, and human maintainer review.

## Do not publish secrets or private data

Never commit GitHub tokens, passwords, private keys, recovery codes, private databases, application profiles, personal contact details, or unredacted diagnostic logs. Use private vulnerability reporting for security issues; do not post exploit details publicly while a vulnerability is unresolved.

## Research integrity

A passing schema/hash validator is not independent mathematical verification. Review provenance and numerical details. A finite numerical calculation is not a proof of the Riemann Hypothesis.
