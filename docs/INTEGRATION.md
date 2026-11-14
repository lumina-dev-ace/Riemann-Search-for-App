# Desktop integration

The desktop reads the public repository `lumina-dev-ace/Riemann-Search-for-App` without authorization. It resolves the manifest commit, fetches immutable content by commit SHA, validates every accepted-range file, and stores a validated cache separately from local research. If live import fails, the UI reports the error and retains the prior local database and cache as stale display data.

Global research begins at the manifest's first-required index. That boundary does not mean the index has been computed. The manifest checkpoint remains `null` until maintainers accept genuine contiguous results. Desktop indexes are exact decimal strings throughout JSON and range validation.

Local experiments run and persist when GitHub is unavailable. Public reads run in a worker thread so they do not block the UI. Export writes a validated JSON record without publishing it.

Optional contribution uses GitHub App device sign-in and a separately deployed server. The desktop never contains the App private key or installation credential; contributors do not configure personal access tokens. The service validates a submission and opens a reviewable PR. It never merges or advances the public checkpoint. Until maintainers configure the App and deploy the service, sign-in stays disabled while public and local features work normally.

The repository validator checks structure, declared verification metadata, content hashes, and consecutive coverage. It does not independently compute or certify a zero, and a finite numerical result is not a proof of the Riemann Hypothesis.
