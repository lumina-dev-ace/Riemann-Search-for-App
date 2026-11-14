# Optional GitHub App contribution service

This source is provided for maintainers who choose to offer in-app proposal submission. It is not necessary for public synchronization or local application use and is not live until configured and deployed.

Install `requirements.txt` from this directory in the server environment. The optional tests use `requirements-test.txt`. Required secret settings are `RIEMANNSEARCH_GITHUB_APP_CLIENT_ID`, `RIEMANNSEARCH_GITHUB_APP_ID`, `RIEMANNSEARCH_GITHUB_INSTALLATION_ID`, `RIEMANNSEARCH_GITHUB_APP_PRIVATE_KEY` (or a protected private-key file path), and `RIEMANNSEARCH_SESSION_SIGNING_KEY` (at least 32 bytes). Set `RIEMANNSEARCH_RATE_LIMIT_DATABASE` to durable storage. Configure the GitHub App for this repository only, with Contents and Pull requests write permission, and enable Device Flow.

Run with an ASGI server such as `uvicorn services.contribution_api.app:app`. Expose it only over HTTPS. The public health/config endpoints disclose no secrets. The proposal route validates records, rate limits submissions, creates a unique review branch, and opens a PR. It has no merge or default-branch update endpoint.

Before setting a service URL in the desktop build, verify `/health`, `/v1/config`, persistent storage, HTTPS, secret handling, and a real review-only proposal on a disposable branch. Keep the service optional and fail closed for contribution requests while public research sync continues independently.
