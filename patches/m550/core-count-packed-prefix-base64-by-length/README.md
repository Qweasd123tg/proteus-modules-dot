# Core: count generated packed-prefix Base64 by length

The derived cache writer no longer walks five already generated Base64 strings just to check their compact JSON length. It charges those exact lengths against the same 64 MiB budget and still uses the same bounded JSON serializer for the schema and arbitrary escaped call IDs. The saved payload, actual final serialization, decoder and validation are unchanged.

The exact candidate passed 38 native tests; the stock control passed the 37 common tests. The new test checks the full serializer at inclusive boundaries, with batched and non-batched Base64 and escaped call IDs. Existing in-process cache tests check owned and borrowed save bytes/operations and failed HEAD behavior. App-server startup/recovery tests include persisted synthetic sessions through the pinned JSONL test worker. No installed Desktop, app RAM, latency or count of bytes written was measured.

Apply only `source.patch` on the exact Core owner in `receipt.json`. No alternate. #801 and #816 composition is source-only, not a combined runtime test.
