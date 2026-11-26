# Core: move prepared history into a durable workflow checkpoint

After the same checkpoint validation and live-history rebase, move the prepared proposed messages into the existing persisted Checkpoint record instead of deep-cloning them for the writer. The separately rebased live history, including independently settled tool results, remains distinct. In-memory checkpoints, validation, revision and attribution, journal and wire format, commit reconciliation, and ACK behavior are unchanged.

Rust 1.95 native checks on the exact patch: 59 Core library tests (59 same-name controls also passed) and three original integration tests linked to the exact candidate Core. The latter cover durable/replayed checkpoints through the pinned reference Rust and in-tree Python workflow fixtures, stale/unbound guards, and a fixture that disregards an accepted preparation ACK. That last test is not a storage transport failure. No installed Desktop or current standalone coding worker check; no process-memory or timing measurement.

Apply only `source.patch` to the exact Core owner in `receipt.json`. No alternate. The two additional replay fixture arguments now pass owned copies; the replay assertions are unchanged.
