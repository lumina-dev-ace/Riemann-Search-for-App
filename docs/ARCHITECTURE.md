# Repository architecture

## Purpose

This repository is intended to provide a public, reviewable research-data network and static progress dashboard for RiemannSearch. The desktop application is responsible for numerical computation and local persistence. The public repository should contain only records and metadata approved for sharing.

## Current repository structure

```text
.github/
  ISSUE_TEMPLATE/
  workflows/
docs/
global/
  checkpoint.json
records/
riemann_network/
schemas/
tools/
website/
  data/
```

- `global/checkpoint.json` contains the current scaffold's checkpoint metadata.
- `records/` contains immutable research-record JSON files.
- `schemas/` defines the current scaffold's data contracts.
- `riemann_network/` provides read-only public access.
- `tools/` validates the data and generates dashboard data.
- `website/` is a dependency-free static site.

## Data flow intended by this scaffold

```text
Desktop local computation
        |
        v
Local database and export
        |
        v
Research record proposal
        |
        v
Pull request and human review
        |
        v
Repository validator and CI
        |
        v
Accepted repository data
        |
        v
Static dashboard build and Pages deployment
        |
        v
Read-only desktop synchronization
```

Local computation and local persistence must never depend on GitHub availability. Public synchronization is read-only. Publication is a separate action and must not rely on a permanent write credential embedded in the desktop executable.

## Contract alignment is a release gate

The final desktop implementation handoff describes a different canonical network contract:

- `data/global_manifest.json`
- `data/ranges/`
- `data/schema/`
- `progress/`

The files currently in this repository use an earlier `global/checkpoint.json` and `records/` contract. These are not interchangeable. The desktop integration phase must inspect the actual final application code and migrate this repository to one canonical contract before any real app-generated research is published.

The current repository data is an empty scaffold. It is not evidence of completed computation. The approved first required index is 10,000,000,000,000, while the completed global checkpoint is still uninitialized.

## Scientific trust boundaries

The repository validator checks structural integrity, declared verification metadata, sequence continuity, and checkpoint consistency. It does not recompute the zeta function. Reviewers must examine provenance and reproducibility before accepting research data. A finite numerical computation or recheck is not a proof of the Riemann Hypothesis.

## Deployment

GitHub Actions validates data and builds the static site. GitHub Pages must be enabled by a repository owner with **Settings → Pages → Source → GitHub Actions**. See [Repository setup](REPOSITORY_SETUP.md).
