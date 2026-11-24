# Modules: decode complete staged display rows from the read buffer

After `OpenDisplaySnapshot` has strictly validated the canonical journal, its
private staging file is used by `ReadDisplayRecords`. The page reader previously
copied every staged line into a separate scratch buffer before decoding it. This
change passes a line already completed in the existing `BufReader` buffer
directly to the same JSON decoder, then consumes the line. Split lines still
use the original bounded-retention scratch flow. Interrupted reads still retry
through `read_until`; a failed decode consumes the same line. The decoder,
wire format, response byte accounting, monotonic cursor, pending row on byte
budget exhaustion, and source revalidation fences are unchanged.

**Base and scope.** Full historical Modules M362 source archive
`31f862e7dc656db04fd87da7b8cf7cdc1348e732ff1a6a35e5d34c9b701b2a37`, with the
exact published #595 and #605 applied (Git tree `6131bc56c1696f007cbe9002dfd7c308c9cc9e62`). Only
`storage/session-storage/src/display.rs` changes:
`92426ea51d9c2a46964a10adf0c31481f95d6b06` to
`31ee79e86344415923de11cbaabbd02edd8d2bfb`. No lock, caps, security boundaries,
durable representation, source identity, or complete canonical validation changes.
The source patch adjusts an existing inline test to exercise both zero-scratch
complete rows and forced split rows, including release of large scratch.

**Verification.** Exact Modules storage source and pinned Core SDK
`0c1b7572313230e5d123e95c722e1258a2e9ecd6`. Rust 1.95.0, distinct baseline and
candidate native binaries, 100 existing tests each under default
`serde_json` and `serde_json/preserve_order`. One upstream ignored benchmark
and the manual 50k fixture are excluded from the automatic suite. Existing
service tests cover rewritten/corrupt pinned sources, external blobs, append
while reading, cursor retries, staged large-row and page-byte limits.

The 50k manual fixture uses real JSONL/SQLite canonical data, real local
`StorageService::execute` requests and response-contract validation. Test-only
instrumentation counts bytes copied into the stage reader's scratch while
forwarding to the unchanged `read_until` implementation. Below the 32 MiB cap,
all four binaries read the same durable corpus; each backend exposed 50,000
records in 200 pages with identical record bytes, state size, source fingerprint
and canonical hashing bytes between arms. Display page reading did not decode
the canonical journal again. Large enough to exceed the cap, the regular fallback
remained available, and no staging page was exposed.

| 50k, no model turns | Baseline | Candidate |
|---|---:|---:|
| Staged record bytes (including line endings) | 53,394,774 | 53,394,774 |
| Rows copied into scratch | 50,000 | 6,508 |
| Bytes copied into scratch | 53,394,774 | 6,949,951 |
| Selected state JSON bytes | 32,689,161 | 32,689,161 |

This avoids 46,444,823 copied bytes (87.0%) in each measured backend/layout.
These are scratch-transfer bytes, **not** peak-memory savings or bytes avoided
from disk. The optimization does not eliminate staging I/O, JSON parsing or
the preceding canonical replay. No end-to-end GUI, latency, or whole-process
RSS/PSS claim.

**Apply and reproduce.** Only `source.patch` is the product diff. In Modules
run `git apply --check source.patch` before applying it. To rebuild the native
test proof with pinned Rust 1.95.0 and a verified Cargo vendor:

    python3 proof.py --modules /path/to/Modules-M362-source.tar.gz \
      --core /path/to/pinned-Core.tar.gz --vendor /path/to/vendor \
      --work /path/to/new-workdir --target /path/to/new-targetdir

The workdir requires approximately 250 MB for fixture journals plus transient
stage and compiler outputs. `--prepare-only` validates source archives, exact
patch application, pinned Cargo resolutions and stages the independent arms.
The four measured native test executables were freshly linked directly to the
same already verified pinned SDK and registry artifacts; the portable builder
uses Cargo and explicitly prevents same-name module build reuse between arms.
