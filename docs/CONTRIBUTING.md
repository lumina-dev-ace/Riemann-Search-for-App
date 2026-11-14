# Contributing

- For software or data-contract changes, use the pull-request template and include bounded tests.
- For a genuine numerical range, export only consecutive committed results from RiemannSearch with computation and Arb verification metadata intact. Do not edit, estimate, or fabricate results.
- Run the validator and tests described in the README. A validator pass confirms structure and integrity; it does not independently recompute zeros.
- Never include a personal access token, private key, local database, logs, local notes, machine paths, or unrelated experiment data.
- Maintainers review provenance, current checkpoint continuity, range hashes, and CI before merging a proposal that changes the shared checkpoint.

Public reading, synchronization, local computation, saving, and export do not require a GitHub account. In-app proposals are optional and use the GitHub App contribution service only when maintainers have deployed it.
