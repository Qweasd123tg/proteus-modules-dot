# Avoid temporary text allocations when paging into the live transcript

**Verified in the R71 focused headless gate.** One Desktop production change with two alternative application forms. No native UI, system timing, RSS or allocator-global claim.

Upstream: `Proteus-harness/Proteus-desktop@b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`. `source.patch` is the independently applicable upstream variant; it factors the existing entry constructor and identity check so page text can be shared before building an entry. `cumulative.patch` is the equivalent after-stack variant (requires earlier #249), reusing its constructor/identity helpers instead of adding them again. These are alternatives, never consecutive changes. Verified by source and focused runtime checks on sealed M150 plus exact #393. #394 has no Desktop source paths.

`Transcript::append_page` creates a temporary `Arc<str>` even when the page row already shares identity and identical text with a live row. It then drops that Arc and switches to the live allocation. Compare the owned incoming text to the live row first and pass the existing Arc to construction when equal. A page still has its own wire payload, maps the first matching live duplicate, assigns a fresh internal counter step even when replacing the exposed key, keeps the wire timestamp when present, and leaves all other row fields from the wire. Intentionally no changes to duplicate rules, missed-ID scanning, identity-map ownership, retain/eviction, Codex, network or protocol.

## Reproduce the focused verification

Inputs: pinned Desktop Git source; sealed M150 Desktop with its original source seal; #393 patch with SHA-256 `87c96e53a64f765f60599998ffb0e9d0374b56e60e5f1bfc1827259d458e32ea`. An existing warmed offline Cargo cache and target with the 125 pinned dependency identities, including contracts Git `7cbc7206f03fac130d05bed2844de275476fedc8`, are required for `--run`. Use the established Rust 1.95.0 setup. No native dependencies, full build, package installs or download needed. Don't start while another lane is building or running matched measurements. One job, no incremental output. Reserve 200 MiB maximum additional disk before stopping and checking with the coordinator; preparation has less than 2 MiB of retained source/packet.

```sh
bash verify.sh --prepare PINNED_DESKTOP_CHECKOUT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393
# After a separate compile admission, with CARGO_HOME and CARGO_TARGET_DIR set to
# absolute paths to the pre-existing offline cache and warmed focused target:
bash verify.sh --run PINNED_DESKTOP_CHECKOUT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393
```

The source-only preflight checks SHA, known seal, lock identities, forward and reverse application, exact projection construction, identical resulting append function, and Rust formatting of new snippets. The run uses exact extracted History/Transcript plus pinned dependencies. The pinned original passed 62/62 Rust tests per arm and sealed M150 after #393 passed 71/71 per arm. Each executable was rebuilt and verified using a distinct compiled-in tier/arm identifier. Three existing GPUI-only tests are excluded by name from the harness (the two native ListState cases and one native TestAppContext case). The rich unit test for duplicate identity, role, namespace, anonymous keys, equal/unequal UTF-8 text, timestamps and retained payload passed on the two candidate builds and the two test-only-overlay baselines. The diagnostic compares exact row payloads, shared text count, changes, historical range/anchor ordinal, next live key and return-to-live changes even when stock and candidate already share the same persisted Arc after building the row.

| Synthetic 50-row accepted newer page after seek | Existing equal text overlaps | Stock → candidate constructor text conversions | UTF-8 text bytes passed to conversion, stock → candidate |
|---|---:|---:|---:|
| Window stops 15 rows before live range, 35 equal overlaps | 35 | 50 → 15 | 54,850 → 16,455 |
| Same window, 7 overlapping rows changed | 28 | 50 → 22 | 54,857 → 24,141 |
| Window stops 75 rows before live range | 0 | 50 → 50 | 54,850 → 54,850 |
| Existing stock forward-seek regression shape, window stops 5 before live | 45 | 50 → 5 | 54,850 → 5,485 |

The fixture obeys the pinned Core HTTP page shape: `start = before.saturating_sub(50)` for these positions. Source: Core `app_server/read_model.rs::transcript_page` and `core/session_store/remote/view/cache.rs::page_from_header`. The charging ledger wraps only the temporary extracted Arc conversion and is not added to production. It counts conversions and copied UTF-8 payload bytes, not allocations from the allocator, CPU time, RSS, server/client decode traffic or GPUI frames. The affected event is the accepted forward page that crosses into the live tail; older/unrelated pages and aligned boundary merges are not claimed to benefit.

Full behavior traces were byte-identical within each tier (digests in `evidence.log`). Prior M150 #274 unified live and seek counters (next live key 151 versus pin 51), so raw traces are intentionally different across tiers. Work totals match across tiers. All four fixtures assert the single exact append splice with 100 retained rows and no #393 eviction. Earlier harness-only failed attempts do not count as evidence.
