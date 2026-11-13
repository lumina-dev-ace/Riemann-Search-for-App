# RiemannSearch network client

A standard-library-only, read-only client for the public shared checkpoint and research records.

```python
from riemann_network import NetworkClient, NetworkUnavailableError

client = NetworkClient(cache_dir="./network-cache")
try:
    checkpoint = client.get_checkpoint()
    if checkpoint.stale:
        print("Showing cached checkpoint; network refresh failed.")
    print(checkpoint.data.status, checkpoint.data.highest_verified_index)
    for filename in client.list_records().data:
        record = client.fetch_record(filename).data
except NetworkUnavailableError:
    print("Network unavailable; continue local work.")
```

The package never writes to GitHub and never requires a token. Treat returned records as remote input, retain local-first behavior, and display a stale-cache indicator when `stale` is true.
