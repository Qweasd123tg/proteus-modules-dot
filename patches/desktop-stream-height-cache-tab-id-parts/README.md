# Desktop: stream the tab ID into the persisted height-key hash

The persisted history key is SHA-256 of the tab ID, a colon, and the lowercase hyphenated durable session UUID. After the earlier #392 change, UUID formatting already used a stack buffer, but constructing the tab ID still made a temporary owned string. This patch visits the existing prefix and payload without joining them. It is not a change to the persisted format. The public owned tab ID builder, Display, parser, session guard, cursor guard and both existing snapshot sync calls are unchanged. On a non-UTF-8 Unix path, the original lossy conversion still runs; the patch removes only the subsequent join.

**Target:** [Proteus Desktop f8cc4017](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268). The two touched files are `crates/tabs/src/identity.rs` and `src/ui/chat/history/height_key.rs`. The stock height key already includes #392. The exact patch also composes in both orders with [modules evidence PR #580](https://github.com/Qweasd123tg/proteus-modules-dot/pull/580); that independent patch is included only to verify composition, not as a prerequisite. Both compositions reverse to all original input bytes. No installation, application build or service deployment is needed to apply the source change.

### Evidence

Single-threaded per-test allocator windows, checked in both debug and release on Linux x86-64, rustc 1.95.0. A request is an alloc, alloc_zeroed or realloc; bytes are **requested sizes**, including the full new size for realloc. Inputs and test reporting are outside the window. Results are not peak or retained memory.

| Measured window | Requests, stock → candidate | Requested bytes, stock → candidate |
|---|---:|---:|
| One durable key: ordinary Proteus path | 2 → 0 | 34 → 0 |
| One key: opaque Codex control | 2 → 0 | 36 → 0 |
| One key: 4,096-byte path | 2 → 0 | 4,109 → 0 |
| One key: malformed Unix path | 4 → 2 | 54 → 27 |
| First accepted 50-row snapshot, complete lifted event branch | 57 → 53 | 26,103 → 26,033 |
| Accepted new revision with a previous base, same lifted route | 12 → 8 | 34,035 → 33,965 |
| Missing history cursor, same lifted route | 8 → 8 | 33,965 → 33,965 |
| Stale/duplicate/foreign snapshot, each | 0 → 0 | 0 → 0 |

Both branches produce the **same complete scroller call traces and bound keys**. The first accepted snapshot binds twice; the change removes two temporary tab ID constructions, not work per transcript row. A missing durable session ID still returns None without allocation. Codex is a key-format control, not evidence that its history uses this Core route.

The proof runs the **72 native tabs tests** plus four height/route tests (including both original height-key tests) in each stock/candidate profile. Four UUIDs × 14 tab ID fixtures independently match Python’s SHA-256 of the old complete byte preimage and every key field. Cases include 55–65 byte padding/block boundaries, empty and relative paths with redundant separators/dots, embedded colons/newlines, Unicode, malformed input, long IDs and varied prefix/base cases. Public formatting and parsing, the single write observed by a rejecting formatter, and owned capacities and allocation windows for 34 Codex ID lengths are checked against stock. No Windows run; unpaired UTF-16 was not tested.

The snapshot exercise runs the pinned SessionCursor gate, pump snapshot arm and sync tail, Session snapshot identity update and feedback, History and Transcript reset/range logic, and the complete production height-key module. The native tabs crate is built intact. The boundaries are a snapshot-only event wrapper, a minimal Session/Chat constructor, logged scroller/GPUI calls, context loading, UI event/row-layout handling and tracing. The terminal disk cache, native GPUI, network transport and full Desktop application are not run. No startup, elapsed-time or RSS savings are claimed.

### Replay on Linux

Use Python 3.11+, Git, and a rustc/cargo/rustfmt 1.95.0 toolchain. The proof never changes its inputs. `SOURCE-PROVENANCE.json` lists each required source file, blob and URL; combine them into a temporary source tree, preserving the paths. Desktop sources come from the revision above and Core contract files from its pinned dependency [7cbc7206](https://github.com/Proteus-harness/Proteus-core/tree/7cbc7206f03fac130d05bed2844de275476fedc8). For example, with both checkouts already available:

```sh
python3 - /path/to/Desktop /path/to/Core /tmp/height-key-inputs <<'PY'
import json, pathlib as p, shutil, sys
desktop, core, dest = map(p.Path, sys.argv[1:])
for name, spec in json.load(open("SOURCE-PROVENANCE.json"))["source"].items():
    source = core if "/Proteus-core/" in spec["url"] else desktop
    out = dest / name
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / name, out)
PY
sha256sum -c SHA256SUMS
python3 proof.py /tmp/height-key-inputs /path/to/vendor /path/to/crate-archives \
    /path/to/Desktop/Cargo.lock /path/to/rust-1.95.0/bin --result /tmp/rerun.json
diff verification.json /tmp/rerun.json
```

The locked standalone workspace needs 37 official crate archives (name-version.crate) and Cargo vendor directories with versioned names. They are the selected projection of a separately verified 49-archive cache. If recreating it with Cargo, copy `Cargo.toml`, `Cargo.lock`, and the stock `crates/tabs` into an empty workspace, add an empty `src/lib.rs` and run `cargo vendor --locked --versioned-dirs /path/to/vendor` with normal registry access. Take the matching archives from the Cargo registry cache. The verifier matches every selected archive checksum against the full Desktop lock, then checks all 1,708 vendor files against the archives; it runs both variants offline and locked in separate fresh workspaces and targets. Codegen/profile details are those of this standalone proof, not a full Desktop release. See `verification.json` for the exact request/byte counts and artifact hashes.
