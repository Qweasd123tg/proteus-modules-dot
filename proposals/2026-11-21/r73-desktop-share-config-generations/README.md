# Share Desktop's accepted config generation across extension projections

**Verified in the R73 focused headless lane.** One production candidate, one patch. No native or live transport run, no timings/RSS, and no remote writes.

## Exact scope and ownership

One patch, independently applicable at Desktop pin `b6a7ec2d8d7e486c8aba01291aa8c89774c4cded`. The same patch applies and reverses on exact sealed M150 plus Desktop #393 and #396. No cumulative alternative needed. #394 and #395 are Extensions-only. Earlier desktop #388 changed unrelated snapshot receipt handling in the session file, not the config path.

- Cold Core session creation calls `Chat::load_config` and reads `/config/local` then `/config`. Both success callbacks already check `config_generation`; accepted values become a whole, immutable replacement in `Chat::apply_config`.
- `ui/chats.rs` emits `SessionChanged` from that change. `ui/extensions/session.rs::state` currently deep-clones `ConfigSummary` once to assemble the update; each admitted package process in `runtime/scopes.rs` then clones the update. If K paths are admitted, stock performs 1+K deep projection copies.
- Cold process start announces its subscribed scope; `Host::session_snapshot` invokes the same projection helper per newly announced process when a prior context in that process cannot reuse the baseline. This independently deep-clones the currently accepted configuration once per such snapshot containing a config. Delayed metadata, same-process repeat announcement, foreign ingress and disabled/state-only projection rules are not changed.
- Move each accepted owned `ConfigSummary` into one `Arc` at the existing assignment. The already-existing clone calls then share only that generation's immutable allocations in the projection. The next accepted config creates its own Arc; an old in-flight projection continues referencing the old immutable generation until dropped. No retained cache or new lookup key. The command-result transport's existing separate copy is intentionally out of scope.
- The projection field serializes `Option<&ConfigSummary>` at the existing field position; no Serde feature/dependency change. Core DTOs, config errors, null shape, transport bytes/counts, 16 MiB frame cap, queue limits, generation/session checks, routing and protocol stay untouched. The transport still reserves and serializes synchronously, then queues only bytes. There is one small Arc allocation per accepted config; an inactive/unprojected chat does not receive any deep-copy savings.

## Executed focused proof

The source gate verified the exact sealed tree and predecessor hashes, applied and reversed the same patch against both inputs, and confirmed the same produced DTO code. Four independently compiled, stamped runs used Rust 1.95.0, one offline locked job, the same 125 lock identities (including Core contracts `7cbc7206f03fac130d05bed2844de275476fedc8`), and the existing warmed target. Each selected Cargo JSON compiler artifact was the exact non-test binary for the input manifest/source, with `fresh:false`. The verifier executed that selected artifact, verified its SHA before and after invocation, and recorded the lock/overlay/tool hashes in `cargo-provenance.json`.

`materialize.py` preserves the production state projection and the exact two outgoing enum variants. It extracts the existing generation guards, scope snapshot-known match, lifetime/core and addressed-session predicates, manifest state/entry selection, subscriber clone and event deduplication logic over minimal non-GPUI carrier types. Live native entity subscription, rehost callbacks, actual subprocess and queue operation are **outside** this run. The probe asserts same-session retained scope suppression, different session acceptance, missing scope, inactive/no Core/preview, no events, entry-only/full control, duplicate/wrong-session events, and stale local/discovered controls. It distinguishes a no-Core `state:null` frame from a valid `state` with `config:null`. It then replaces the resident config and keeps older emitted projections live alongside the new generation.

All output bytes were identical in both arms and tiers: SHA-256 `9473181fca3601f20ce35280b4dd56e2d1f954b25d86748e9e06cc4c4e410525`. Different owned profile-buffer addresses were observed in these cases (same generation compared with its resident source, or subscriber with the projected event):

| Synthetic fixture | Projection + subscriber + cold copies before → after |
|---|---:|
| 8 model options, one subscriber and one cold read | 1+1+1 → 0+0+0 |
| 512 model options, three subscribers and three cold reads | 1+3+3 → 0+0+0 |

The fixtures include pending state, nulls, Unicode, opaque nested field insertion order, negative zero and u64::MAX. This proves the ownership mechanism on the exact code slice, not system allocator counts, queue performance, latency or RSS. Native regression checks remain separate: cold/open/reconnect in a synthetic chat with multiple active packages, stale-response/error and rehost lifecycle behavior, and real frame/admission limits.

## Reproduce

Use the pinned upstream checkout and sealed M150 source/receipt below. For runtime execution use Rust 1.95.0 and absolute `CARGO_HOME` and `CARGO_TARGET_DIR` already warmed with the locked dependencies; don't run alongside another compile or matched measurement. Reserve at least 512 MiB and stop for coordination before +200 MiB growth.

```sh
bash verify.sh --prepare PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396
bash verify.sh --run PINNED_DESKTOP_GIT SEALED_M150_DESKTOP SOURCE_SEAL PATCH_393 CUMULATIVE_PATCH_396
```
