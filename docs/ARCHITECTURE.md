# Repository architecture

The GitHub repository is the only public source for shared progress. The desktop app uses the unauthenticated GitHub API and immutable raw URLs to fetch `data/global_manifest.json` and every referenced range file. It validates schema versions, manifest and file hashes, exact index strings, consecutive coverage, and recorded FLINT/Arb metadata before displaying a live checkpoint.

Local computation, persistence, and export stay independent of GitHub. A missing or unavailable public manifest cannot overwrite local results. A cached import is shown as cached/stale and cannot authorize a new global continuation until a live refresh succeeds.

```text
Local FLINT/Arb computation -> local SQLite and checkpoint
                               | explicit export or optional submission
                               v
                     validated range proposal
                               v
                     maintainer review and CI
                               v
              data/global_manifest.json + data/ranges/
                               v
          public desktop synchronization and progress site
```

The canonical contract is `data/global_manifest.json`, `data/ranges/`, and versioned schemas under `data/schema/`. The legacy `global/`, `records/`, `schemas/`, `riemann_network/`, and `website/` trees are retired and must not be used by the desktop or site.

The first required index is `10,000,000,000,000`; it is not completed progress. The current initial checkpoint is `null` with no accepted ranges. The validator checks structure and integrity, not the truth of a contributor's numerical claim. Finite numerical work is not a proof of the Riemann Hypothesis.

The optional proposal service uses a GitHub App installation credential held only on its server. Public reads, local computation, saving, and export need no account. The service creates proposal branches and pull requests; it cannot merge them or directly update the main checkpoint.
