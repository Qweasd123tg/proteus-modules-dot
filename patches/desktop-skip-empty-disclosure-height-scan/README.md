# Desktop: skip the height-disclosure scan when all four stores are empty

This patch adds an early return in `Chat::disclosed_height_rows` when `expanded`, `full_blocks`, `open_chains`, and `tool_diffs` are all empty. The original loop, affected-row merge, and disk exclusion coordinates remain unchanged for any nonempty store. The caller is byte-for-byte unchanged, including the scroller update when there are no exclusions. This is distinct from the row-key set optimization in #535, which runs during splice reconciliation.

- **Upstream:** [Proteus Desktop at `f8cc4017`](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268)
- **Target:** `src/ui/chat/history.rs`, stock blob `297ba38317f47d1801973dddd56344f86085e0e9`, candidate blob `72083028e592d9f7e981a67e800a6367438251a0`.
- **Source-work proof:** 50 → 0 resident row visits on the initial 50-row snapshot; 200 → 0 on a changed live suffix with a retained 200-row archive. Both exercise `History::apply` followed by `Chat::apply_history_changes`; neither calls the helper directly.
- **Behavior proof:** seven paired tests in both debug and release, including 256 combinations of disclosure state and 12 exact range controls. The full scroller call trace is unchanged. The tests cover overlap/coalescing and gaps, both supported block slots, unsupported slots, off-window keys, generic tool chains, a terminal split, a typed subagent progress peer, an absent range, ordinary paging, an unchanged revision, and an independently empty Codex display.

On the all-empty path, the old loop visits each row and evaluates five membership expressions (two block slots). That count is not a claim about hashes or elapsed CPU time. The guard adds short-circuit emptiness checks to the populated path, which still visits the same rows. No allocation, process memory, native frame time, or application startup improvement was measured.

## Reproduce

`source.patch` applies directly at the pinned Desktop root. `proof.py` copies only the pinned source files to a temporary directory; it does not edit the input checkout. Create a small staging tree `SOURCE`: copy the seven `src/` files from the pinned Desktop checkout and the five `crates/proteus-contracts/src/` files from the pinned Core checkout, preserving the paths in `SOURCE-PROVENANCE.json`. The Core pin is Desktop's `proteus-contracts` dependency, `7cbc7206f03fac130d05bed2844de275476fedc8`.

```sh
sha256sum -c SHA256SUMS
python3 proof.py /path/to/SOURCE /path/to/VENDOR /path/to/rust-1.95.0/bin
```

`VENDOR` is a Cargo vendor directory compatible with this standalone proof's `Cargo.lock`; the proof runs offline and locked. To recreate it when network access is available, copy the packet's `Cargo.toml` and `Cargo.lock` into an empty temporary crate with an empty `src/lib.rs` and run Cargo 1.95's `cargo vendor --locked /absolute/path/to/VENDOR` there. These are the proof crate's dependencies, not the Desktop workspace dependency graph.

The lift copies the synchronous history decisions, transcript reset/paging methods, affected-range logic, and protocol types from the exact inputs. Counting is added only to a separate pair of lifted builds; an uninstrumented pair checks effect parity independently. GPUI entities, scroller state, height-key binding, the context-seek boundary, and startup trace output are test adapters. The result verifies calls and their order at those boundaries, not native GPUI rendering, height-store behavior, network fetching, or timings. `evidence.log` records a clean replay.
