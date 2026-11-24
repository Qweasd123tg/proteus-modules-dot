# Borrow pending effect payloads during strict turn settlement

The strict journal validator used to build a temporary vector of deep-cloned ToolResults for every eligible pending effect before it began settlement. The durable effect ledger still has the originals, and bound results need a separate canonical capture as well.

The patch snapshots the existing immutable im::HashMap root and borrows each eligible ToolResult from its actual lifecycle owner. It does not mutate either map or its iteration order. Same matching root/turn/thread, pending/nonfinal filters, actual ordered canonical binding capture, active-ID and stable-part checks, revision/interruption behavior, capture-owner reset and error order. Accepted captures still clone a ToolResult into their new canonical owner; unbound effects don't need a payload clone just to be rejected. The original ledger is not removed.

Production is only source.patch on Core b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14. The original facts.rs blob 79d35068789ee30c0ccac1641b828b3865c0b2ef becomes fdef0aa7a2a430a099fe19269af38a15aecd2214. This is not R288's no-store revision change or R287's transcript copy. There is no savings claim for pure text or already-finalized effects.

## Exact measurement boundary

Pinned native release in both Serde layouts and genuine im 15.1.0 with its default thread-safe configuration. Both exact arms start from the same originating validation state and HAMT root, not independently randomized maps. Synthetic typed journal inputs reach actual strict sequence and facts validation; separate adversarial controls can modify a candidate's internal state to test errors not accepted as durable input. The native validator and real HistoryCapture are under test, not an installed Worker process or full Desktop startup.

The scoped, current-thread ledger counts requested Layouts for eligible-effect prepare, the im clone itself, capture/validation and total settlement separately. It treats successful realloc as old request freed plus new request allocated. Test-only observer bookkeeping is excluded. The pointer observations compare live, simultaneously owned data: original ledger effect, actual iterator or collected input, and genuinely captured canonical result. The measurement does not include OS pages, RSS/PSS, broad CPU/timing, end-to-end or process peak or production traffic frequency.

## First observed result

Both Serde layouts passed 48 paired strict-settlement cases, including 38 actual pending-owner scopes, with four genuinely late mutable-candidate validation failures per layout. Tests use physical synthetic typed JSONL followed by the real sequenced validator; this is not an end-to-end native Worker journal codec statement. The tested mutable validator paths, including deliberate late identity/part conflicts, reproduce the exact partial state on error. The originating COW state and original lifecycle Arc identities remain unchanged.

For 8 MiB raw output per eligible effect, actual ephemeral prepare traffic removed was:

| Fixture | Default requested bytes / allocations removed | preserve_order bytes / allocations removed |
|---|---:|---:|
| One bound effect; canceled settlement | 8,389,810 / 9 | 8,389,702 / 10 |
| Three mixed effects, two bound and one unbound; success | 25,173,211 / 64 | 25,171,391 / 73 |
| One mixed unbound effect; failed status | 8,391,433 / 22 | 8,390,933 / 25 |

Both layouts measure zero requested allocation bytes for the map clone itself. The candidate's prepare consistently makes only the same existing 168-byte HAMT iterator scratch allocation as the empty-effect control. It does not construct a temporary ToolResult payload or collection. On actual visits, candidate borrows the original live ledger result and stock visits a distinct temporary. Each accepted canonical result keeps its separate required String allocation, typed output/capacities and clone cost in both arms. An unbound visit causes zero allocation traffic inside capture. The overall measured settlement scope's allocation and free differences equal the prepare difference; it returns identical net requested ownership.

Pending walk order matches the same originating map, even when the observed visitation order differs from the declared canonical binding order. The proof covers absent/previous/nested/detached and final-precedence filtering, malformed envelope, cancellation interruption and saturated revision, competing known-part/active-ID failures after an earlier insertion, exact partial state and capture resets, and no extra work for the no-capture case. One- and four-MiB counterparts and small mixed/empty controls are also retained. No RSS, overall peak, CPU or startup extrapolation.

GATES.md records the original gate. The first two raw files and both checkers are supplied along with binary/build/provenance receipts. Portable staging verified 138 pinned source donors, 152 exact locked registry archives and 8,573 members, the exact generated proof and both feature layouts. Replay locally with python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run. The supplied portable run was staged; actual native runs used the verified shared offline build lane. Nothing was published.

## Raw receipt transport

The original JSONL receipts are stored as Base64-wrapped gzip. Decode them before running the receipt checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
