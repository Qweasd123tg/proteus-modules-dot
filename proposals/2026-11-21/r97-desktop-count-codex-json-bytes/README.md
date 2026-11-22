# Count Codex event JSON bytes without building the output String

Proteus Desktop proposal for `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`, verified on the original source and the sealed M150 Desktop stack through #419. Only `src/agents/codex/router.rs` changes.

The Router needs a compact JSON byte count, not a copy of the serialized bytes. It now writes the same non-alternate `Display` representation into a checked UTF-8 byte counter. This affects pending request params, projected Plan and Usage values, and tool inputs, including tools in a resynced history. The full formatting traversal still happens at every original accounting site. Raw frames, projection/display clipping, queue and transport limits, routing and interaction handling, rejection and disconnect policies, and budget release are unchanged.

## What passed

- Eight separately compiled, Cargo-selected Router test executables: original vs cumulative source, before vs after the change, and sorted vs insertion-order JSON maps. All **13/13** tests passed in each configuration: nine existing Router cases and four focused cases. Their behavior traces matched exactly. No GUI or Codex service was launched, and the transport subprocess tests were not run.
- Full charges matched the original compact String oracle for 15 representative JSON values, including UTF-8, escaped and control characters, integer extrema, signed zero, exponent floats and nested arrays/objects. Real projection and routing preserved pending request/plan/usage/tool contents and order. Snapshot item sums, text slack, exact byte-budget acceptance, one-byte-over handling in startup and registered queues, and release on consumption or final channel drop were checked. Boundary cases used a seeded test counter, not a large stream.
- In one **93,635-byte compact JSON** fixture, each pending params or tool input count went from **15 allocation/reallocation requests totaling 262,136 bytes to zero**. The same two tools in one resync went from 30 / 524,272 to zero. A 10-byte plan went from 2 / 24 to zero, and a text delta stayed at zero. Counts are scoped to `event_bytes` on prebuilt events, excluding projection and queues. Summed allocation requests are **not** peak memory, retained memory, RSS, or a speed measurement.
- 49 prior Desktop patch hashes and 22 locked external dependency identities verified. No prior proposal touched the Router file. Each arm compiled its actual local codex-client library; the stock and cumulative transport files differ. `cargo-provenance.json` binds the distinct test executables to the exact inputs, Cargo lock, profile, features, and executable hashes before and after each run.

## Reproduce

Verify the packet with `sha256sum -c SHA256SUMS`. Run `bash verify.sh --prepare WORKSPACE_WITH_PINNED_INPUTS` for static composition. For the isolated, locked, offline, one-job focused check, set `CARGO_HOME`, `CARGO_TARGET_DIR`, `R97_BUILD_LOCK`, and `R97_RAW_CARGO_DIR` as in the build environment and use `--run`. It requires the existing Desktop dependency cache and common compiler lock; check the disk floors before starting. This is a focused Router test, not a full desktop build or end-to-end run.
