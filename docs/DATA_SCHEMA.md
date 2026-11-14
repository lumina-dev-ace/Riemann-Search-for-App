# Research data schema

The repository is the single public source of global progress. `data/global_manifest.json` is version 1. All zero indices are canonical decimal strings so JSON or database consumers cannot round them through floating point or signed 64-bit limits.

## Network initialization

An `uninitialized` manifest has null `first_required_index` and null `global_checkpoint_index`, and empty range/history arrays. It makes no claim about a starting point. An `initialized` manifest names `first_required_index`, which is the next index from which this network accepts work. The configured start is 10,000,000,002,278, immediately after the legacy desktop's latest locally completed index, 10,000,000,002,277. This starting boundary is not itself a published result. Before any accepted work, `global_checkpoint_index` remains null and the website displays that no range has yet been accepted.

After publication, `global_checkpoint_index` must equal the final result index of the consecutive accepted ranges beginning exactly at `first_required_index`. Every next range must start at the prior endpoint plus one. Gaps, overlaps, duplicates, stale-base commits, or a range endpoint that disagrees with its actual result list are rejected.

## Integrity

Manifest and range `integrity.sha256` values are SHA-256 of canonical UTF-8 JSON with sorted keys and compact separators, excluding the `integrity` member itself. The manifest additionally lists the SHA-256 of the exact serialized range file bytes. The desktop and CI validate both hashes, each result index, the derived endpoints, and every referenced range before accepting an import.

Hashes detect corruption and mismatch; they do not establish author identity or mathematical proof. Git commit history records publication provenance. The numerical record must identify FLINT/Arb versions, algorithm, computation precision, verification method/precision, per-result residuals, statuses and interval enclosures when the backend stored them. Computation and verification durations are decimal strings (or null) so Python and browser implementations hash the same exact JSON value without floating-point reformatting. A numerical verification status is not a proof of the Riemann Hypothesis.

See `../data/schema/global_manifest.schema.json` and `../data/schema/research_range.schema.json` for JSON Schema definitions.
