# Contributing research data

1. Keep an untouched backup of your local RiemannSearch database.
2. Export a research record using the published schema.
3. Check the contributor pseudonym, app version, index sequence, backend, and precision.
4. Run `python tools/validate_network.py`.
5. Submit the record and a checkpoint proposal through a pull request.

Do not publish personal information, API tokens, private database files, experimental binaries, or unverified data. Use a display name or pseudonym; never add email addresses to record metadata.

Until a secure publishing service and contributor identity policy exist, contributors should submit pull requests rather than write directly to the main branch. A passing validator is a structural check, not a mathematical re-computation.
