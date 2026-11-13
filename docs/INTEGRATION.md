# Desktop application integration

This repository now includes the credential-free Python read client in `riemann_network/`, as well as the public data contract, validator, and static dashboard. The RiemannSearch desktop application source itself is not currently in this repository, so this commit cannot yet wire the client into its PySide screens.

## Reading the network

The client is standard-library-only and reads the public `global/checkpoint.json` and `records/*.json` files. Example:

```python
from riemann_network import NetworkClient, NetworkUnavailableError

client = NetworkClient(cache_dir="path/to/app-cache")
try:
    checkpoint = client.get_checkpoint()
    if checkpoint.stale:
        # Show that this is cached/offline data in the UI.
        pass
    if checkpoint.data.status == "initialized":
        highest = checkpoint.data.highest_verified_index
    else:
        highest = None  # Never treat uninitialized as zero.
    record_names = client.list_records()
except NetworkUnavailableError:
    # Keep the app usable; local computation and saving continue offline.
    pass
```

Use HTTPS and a configurable repository/ref. The client labels stale cache responses. The app should show last-sync status and must not block computation while fetching remote data.

## Publishing workflow

Publishing must be a separate, explicit action after local persistence:
1. Export the exact contiguous sequence from the latest global checkpoint + 1 through the proposed end index.
2. Confirm every index exists exactly once and that all entries intended for checkpoint advancement are Arb-interval verified.
3. Fetch the latest checkpoint immediately before submitting the proposal.
4. Reject proposals that overlap, skip indices, or fail to extend the current global checkpoint.
5. Submit the record and checkpoint proposal for maintainer review.
6. After acceptance, re-read the repository and store the resulting commit SHA locally.

The read client intentionally has no write method. A client-side read-then-write flow is not race-safe. Direct publishing requires a trusted server-side transaction or a carefully serialized compare-and-swap update. Never force-push. Never embed a permanent personal access token, GitHub App private key, or other secret in the desktop executable.

## Local-first guarantees

- Save numerical results and experiment state locally first.
- Offline or rejected publication leaves local data unchanged.
- The global checkpoint never decreases.
- Keep rejected exports available for review and retry.
- Candidate rows, attempted ranges, and a high-water setting are not completed consecutive zeros.
