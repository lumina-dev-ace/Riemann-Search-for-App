# Data format and trust model

See `schemas/research-record.schema.json` and `schemas/checkpoint.schema.json` for the versioned JSON contracts.

A record contains an inclusive index range and one entry per index. Each ordinate is represented as a decimal-string interval. Entries may be `candidate`, `evaluated`, or `arb_verified`. Only an entry with status `arb_verified`, verification method `arb_interval`, backend `FLINT/Arb`, and `certified: true` can count toward the authoritative global checkpoint.

The validator checks JSON shape, unique and contiguous indices, decimal interval ordering, and declared verification metadata. It does **not** recompute the zeta function or independently validate Arb computations. The application must only export `arb_verified` metadata after the authoritative FLINT/Arb pipeline has actually produced the corresponding rigorous enclosure.

The checkpoint is monotonic: it advances only if every index from 1 through the proposed value is represented exactly once and is verified. Candidate-only or evaluated-but-unverified entries do not count. Concurrent proposals must be serialized; stale writers must be rejected.

Finite numerical verification is not a proof of the Riemann Hypothesis.
