# One-time repository setup

The repository files and CI workflows are committed. Two GitHub repository controls still need owner-side configuration because the connected GitHub integration cannot change these settings.

## Enable the dashboard deployment

1. Open the repository **Settings**.
2. Select **Pages** under **Code and automation**.
3. Under **Build and deployment**, set **Source** to **GitHub Actions**.
4. Return to the **Actions** tab and check the latest **Deploy research dashboard** run.

The workflow already requests the minimum Pages deployment permissions and attempts automatic enablement. GitHub rejected the automatic site-creation request for the connected workflow integration, so the initial Pages setting must be created by a repository owner. Once enabled, future qualifying pushes run the static dashboard deployment.

## Protect the main branch (recommended)

Under **Settings → Branches**, add a branch protection rule for `main`:
- Require a pull request before merging.
- Require the **Validate research data / validate** status check.
- Do not require an approval count until another trusted maintainer is available; GitHub does not permit authors to approve their own pull requests.
- Restrict force pushes and branch deletion.

The repository includes `.github/CODEOWNERS`, but CODEOWNERS review requests are not enforced until branch protection or a ruleset requires them.

## What is already configured in the repository

- A read-only, credential-free desktop client.
- A versioned research-record and checkpoint contract.
- A structural validator and automated unit tests.
- A static dashboard and GitHub Pages deployment workflow.
- Minimal workflow permissions, no publishing secrets, and no permanent write token in the app.

## Still needed before real collaboration

The desktop app source must be added and the client wired into the actual PySide UI. The record schema must be checked against the app's real FLINT/Arb export format before accepting scientific data. A trusted, race-safe publishing service is also still required for direct in-app publishing; until then use reviewed pull requests.
