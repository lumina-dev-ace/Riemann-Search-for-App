# One-time repository setup

The repository contains validation and security workflows, a static dashboard, and a preliminary data-network scaffold. Some repository-level settings require an owner to configure them in GitHub Settings.

## 1. Enable GitHub Pages

1. Open the repository **Settings**.
2. Select **Pages** under **Code and automation**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Open **Actions** and inspect the latest **Deploy research dashboard** run.

The workflow uses the official Pages actions and minimal deployment permissions. The initial Pages site must be enabled by a repository owner. Once enabled, qualifying pushes can deploy the static dashboard.

## 2. Protect the main branch

Under **Settings → Rules → Rulesets** (or **Settings → Branches**), create a ruleset targeting `main`.

Recommended rules:

- Require a pull request before merging.
- Require the `Validate research data / validate` status check after confirming its exact name in a completed workflow run.
- Block force pushes.
- Block branch deletion.
- Require conversation resolution.
- Require CODEOWNERS review when a second trusted maintainer is available.

Do not require an approval count of one while the repository has only one maintainer; authors cannot approve their own pull requests. Keep bypass rights restricted to the owner and use them sparingly.

## 3. Enable security features

Under **Settings → Code security and analysis**, enable the available options for:

- Dependabot alerts.
- Dependabot security updates.
- Secret scanning and push protection, where available for the repository.
- Private vulnerability reporting.

The repository includes a CodeQL workflow and Dependabot configuration. Those workflows do not replace repository-level security settings.

## 4. Workflow permissions

Under **Settings → Actions → General**, keep the default workflow token permission read-only where possible. Individual workflows request only the permissions they need. The Pages workflow needs Pages write and OIDC token permissions for deployment; validation and CodeQL do not need repository write access.

## 5. Public use and contributions

Public research browsing and synchronization are intended to work without a GitHub account or personal access token. A GitHub credential must not be required for normal application use. Contributions and publication are separate workflows and must be protected by review or a secure server-side publishing service.

## 6. Current integration blocker

The final desktop implementation handoff describes a manifest-and-range format:

- `data/global_manifest.json`
- `data/ranges/`
- `data/schema/`
- `progress/`

This repository currently contains an earlier `global/checkpoint.json` and `records/` contract. These formats are not interchangeable. The desktop integration phase must migrate the repository to one canonical contract before the application can use it for authoritative global progress or publish app-generated research.

The approved first required index is 10,000,000,000,000. It is not a completed research result. Keep the global checkpoint uninitialized until genuine consecutive verified records are accepted.
