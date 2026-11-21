# Core: pre-size the live turn snapshot row vector

Base: Proteus-harness/Proteus-core `32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f`.

`TurnProgress::snapshot()` previously cloned the live row vector and then
extended it from separately cloned failed-queue and background-card vectors.
It now allocates the full row capacity once and clones each slice directly
into the owned snapshot. The optional submitted row is built in the same
position with the same timestamp, text and images. The resulting rows still
own their nested members. No cache, shared mutable data, read-model changes,
or change to lock scope, journal, HTTP/SSE schema, policy, or admission.

The M100 #288 patch touches only the different compact JSON preview helper
in the same file. M100 roster, R57–R61 Core patches and GitHub progress snapshot
search found no competing row-vector change. No other code was modified.

## Results

- 33/33 isolated Rust tests: all 15 existing `turn_progress` tests on each
  exact source side, plus three paired probe tests.
- 192 byte-identical JSON snapshots across live/submitted/failed/background
  combinations. Independent nested ownership was verified by editing one
  returned snapshot and rereading the same captured state. Native module
  tests exercise actual event application for reasoning, tools, turns,
  attachments, child cards and timestamps.
- Two completed runs produced the same corpus hash and allocation counts.

| Synthetic snapshot | Allocation requests | Requested bytes | Row capacity |
| --- | ---: | ---: | ---: |
| Eight live rows, no tail | 55 → 55 | 8,161 → 8,161 | 8 → 8 |
| One submitted prompt | 3 → 3 | 2,586 → 666 | 4 → 1 |
| Eight live rows, two child cards | 110 → 108 | 23,459 → 13,219 | 16 → 10 |
| Image-only submission, three failed queue rows, two child cards | 77 → 74 | 15,163 → 8,123 | 8 → 6 |
| Stress: four live, 32 failed, 64 background rows | 1,719 → 1,715 | 272,073 → 185,033 | 100 → 100 |

Counts include successful allocation/reallocation requests within the one
synchronous snapshot call; prep, JSON serialization, completed-history
merge, response transport and later drop are outside scope. Capacity refers
only to the live row vector, not total retained memory. No RSS/PSS, peak,
wall-time, or whole-runtime claim.

## Reproduce

Use a clean checkout of the pinned Core and the actual stock locked artifacts
from one target/deps directory, built with the same compiler as the probe.
The artifact hashes and compiler used here are in `gates.log`. Have
`rustc` and `ld.lld` on PATH.

    git -C "$exact_core" apply --check "$packet/source.patch"
    python3 "$packet/probe.py" "$exact_core" \
      --contracts-rlib "$stock_contracts" --serde-json-rlib "$stock_serde_json" \
      --uuid-rlib "$stock_uuid"

The fixture adapter is appended to a temporary copy for testing only; the
production patch modifies only the original snapshot method. Forward,
reverse/byte restoration, `git diff --check`, workspace and harness formatting,
and M100 plus seven later Core patches apply-only passed. Full Core Cargo,
HTTP/SSE integration and cumulative runtime were not run for this narrow
change under shared build resource limits. No remote writes.
