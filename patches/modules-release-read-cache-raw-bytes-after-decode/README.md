# Modules: release the ReadCache file buffer after decoding

**Production diff: `source.patch` only.** It applies to Modules
`331cfc20bbaf821ab07de49868426da29ebdeb64` and releases the owned file buffer
after the cache envelope decodes into an owned snapshot and JSON value. The raw
bytes are no longer retained during source checks, the canonical ETag hash, or
the final locator recheck.

The file is still opened and verified as regular, read to EOF with the same
bounded `maximum + 1` rule, and rejected above the same 65 MiB envelope cap.
The 64 KiB allocation hint, JSON validation, source comparisons, ETag, second
locator check, and response are unchanged. No disk bytes or transport format
change. File closure already occurs before the read helper returns the buffer.

## Results and limits

The primary test writes a **real, valid 3,146,223-byte cache envelope** into a
private directory using the actual worker envelope type and hash-derived
filename. Its typed tool body is the synthetic 3 MiB nested args/effective-args
fixture used by [#574](https://github.com/Qweasd123tg/proteus-modules-dot/pull/574).
The fixture confirms that body’s independent canonical ETag
`71d6fec7008162511c63419d5f3254190290dd567b4dfe3ac730a7e1140abd17`.

| Requested allocation bytes during that read, release | Before | After |
| --- | ---: | ---: |
| At canonical ETag entry, default map | 7,345,066 | 3,150,762 |
| At final locator entry, default map | 7,345,130 | 3,150,826 |
| At canonical ETag entry, preserve-order map | 7,343,969 | 3,149,665 |
| At final locator entry, preserve-order map | 7,344,033 | 3,149,729 |

In both maps the exact **4,194,304-byte raw Vec allocation** is live in stock
and already released in the candidate at both observations. An allocation
generation and its actual capacity are measured, not estimated from disk
length. Absolute totals include the synthetic locator path length and can vary
with the replay directory. Allocation and reallocation counts are unchanged. The interval still
includes raw+typed decode coexistence: the same fixture's inclusive requested
high-water changes by just **200 bytes**, not 4 MiB. This is neither process
RSS/PSS nor a latency, startup peak or real-world hit rate measurement. The
worker SDK already constructs its reply after the raw buffer would have dropped
in stock. Missing cache files and first-build cold misses have no raw payload
at either observation. The large tool and additional packed-prefix-shaped
fixture do not establish that a particular normal startup reads those objects.

## Verification

23 paired cases in each combination of debug/release and the two real
serde_json map implementations, with actual bounded regular-file reads,
pinned Serde and Ring, exact success wire/error parity per layout, independently
ordered canonical ETags, and named stage counters. Cases include source identity
and snapshot-handle controls, first/second locator rejection, absent/nonregular
files, malformed/truncated/trailing/duplicate/unknown envelope fields, valid
65 MiB with trailing whitespace and rejection at 65 MiB + 1, small/hinted and
multi-MiB bodies. The mismatched source skips the hash and second locator, as
before. The proof records the exact requested allocation alive at each witness
and checks that all measured read/response allocations are eventually freed.
An injected locator adapter observes the calls and tests their rejection; it
does not run native incarnation/locking logic, full worker IPC, full Core
startup, or a journal replay. No hash error is fabricated for a valid Value.

The replay uses a source-bound Rust slice, 36 official registry archives
checked against the Modules lock and its locked Core SDK, and pinned Linux
x86-64 Rust 1.95.0 tools. It checks the entire product file with rustfmt and proves
ordinary forward application and exact reverse. Use `SOURCE-PROVENANCE.json`
to stage read-only input paths beneath `refs/modules`, `refs/sdk` and
`refs/core` at their listed revisions. In addition, provide the SDK's
`refs/sdk/Cargo.lock` (blob `a9dbb28155a2d48753591f1a4391d9863d42314b`).

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /fresh/replay \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-crates
```

Repeat `--archives` for a scattered archive set. A local native C toolchain is
required to build Ring and is not part of the Rust toolchain hashes.
