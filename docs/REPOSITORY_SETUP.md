# Repository setup

## Public read access

The repository is public. No token or GitHub account is required for desktop manifest/range synchronization, local computation, saving, or export. Do not put public-read setup behind a credential prompt.

## Protect the main branch

Configure a ruleset for `main` that requires a pull request and the successful `validate` check. Block force pushes and limit bypass permissions. Confirm the exact status-check name from a recent workflow run before enabling the rule.

## GitHub Pages

Set **Settings → Pages → Build and deployment → Source** to **GitHub Actions**. Pages publishing runs after a validated update reaches `main`, or by explicit `workflow_dispatch`. The workflow requests only contents read, Pages write, and the OIDC deployment token.

## Security workflows

The repository retains PR #1's CodeQL workflow, Dependabot configuration, issue forms, security policy, and contribution guidance. Enable Dependabot alerts, security updates, push protection, and private vulnerability reporting in repository settings where available. Keep Actions' default `GITHUB_TOKEN` permissions read-only.

## Optional contribution service

Normal app use does not require authentication. The optional GitHub App proposal service remains disabled until an owner registers the App, configures its server-only secrets, and deploys it with persistent storage. See [publishing](PUBLISHING.md). Never embed an App private key or PAT in the desktop binary. The service opens proposal PRs only; maintainer review is required for any main-branch/checkpoint change.

## Research boundary

The approved first-required index is `10,000,000,000,000`; `global_checkpoint_index` is `null`; `accepted_ranges` is empty. These values stay so until real, consecutive, verified results are reviewed and accepted. Failed local historical rows are not eligible for import.
