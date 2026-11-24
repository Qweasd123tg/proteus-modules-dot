# Move exact-fit staged transcript text into its display row

Target: [Proteus-core b2d2e6de](https://github.com/Proteus-harness/Proteus-core/tree/b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14). This patch changes three private renderer files under `crates/proteus-core/src/app_server/`. Apply with `git apply --check /path/to/source.patch` followed by `git apply /path/to/source.patch`.

When the cold transcript renderer scans a certified local spool, it receives an owned, decoded journal record. For a visible Append message with exactly one ordinary Text part, that String can be the row's text. Stock instead makes a second String from its bytes while the decoded donor still exists. The patch moves the donor **only when its capacity equals its length**. An oversized donor is copied as before so a small row cannot keep a large buffer alive. Output always uses the same row constructor and identity indexes. Canonical session state is not the donor.

The fast path collects record timestamps before rendering, skips the same live turn, and inserts the part identity before scope or Unicode-whitespace filtering. Trimming decides visibility only; emitted text, role, phase, ID and timestamp are unchanged. Non-Append events still use the stock renderer. Multipart/non-text messages in an Append still use the original message filtering and rendering body, in order. General replay, certification, staging validation, cache generation, hard resets, tool finalization and prefix handling are not optimized here. #567's raw scratch change is a separate file and allocation; its savings must not be added as if a shared native peak had been measured.

## What was measured

A physical 32,714,257-byte JSONL spool held one synthetic HistoryMutated Append with 50,000 alternating User/Assistant, single-text messages. It uses the public long fixture's text shape with four repeats and fixed IDs, not an owner session or byte-identical recording. Both arms decoded the spool with official locked serde_json 1.0.151, serde 1.0.228 and UUID 1.23.1. The comparison checks full serialized transcript bytes, **every** output text pointer against its own actual decoded donor, and allocation requests during the handoff/render (not deserialization).

| 50k handoff/render | Stock | Candidate |
|---|---:|---:|
| Allocation requests, excluding reallocations | 100,060 | 50,060 |
| Reallocations | 14 | 14 |
| Requested allocation + reallocation bytes | 100,687,138 | 80,998,248 |
| Sum of final row text capacities | 19,688,890 | 19,688,890 |
| Output texts reusing their decoded donor | 0 | 50,000 |

The difference is **50,000 allocations and 19,688,890 requested bytes** (18.78 MiB) avoided within this staged fixture. It is not 18.78 MiB less permanent row storage. A 16-row control avoided 16 allocations/6,246 bytes. A 390-byte text deliberately given an extra 1 MiB *after decode* produced a 390-byte row and the same 6 allocation requests/2,854 bytes in both arms. The first, rejected unguarded version retained those spare bytes; the final patch does not.

The proof also checks byte-for-byte stock/candidate output against the stock general replay for certified fixtures, including a witnessed model response, live-skipped part rehosting across a backwards clock, hidden or blank duplicates, non-normalized phase, NUL and surrounding Unicode whitespace, multipart text, tools/results, images, late reasoning insertion, compaction and failure settlement; plus 96 generated combinations. Uncertified hard-reset and hosted/citation cases exercise the unchanged general fallback in both arms. A valid row followed by malformed JSON, missing LF, wrong final count, or an injected late scan error produces an error, never partial returned rows.

Release timing uses the same physical input for both arms, pinned to one CPU, with three warm-up pairs followed by 25 paired comparisons (both orders). The whole window includes rewind/read, decode, render, finish and dropping the returned rows. A separate process-CPU window covers only the render callback, including disposal of the owned record, not deserialization. Small and mixed cohorts repeat each arm 150 and 50 times per pair; the 50k cohort runs once per arm per pair. Timings are synthetic warmed-file measurements, not cold disk or native startup latency. See `SOURCE-PROVENANCE.json` for observed medians, p10/p90 and order splits. The gate flags median >1.10, p90 >1.25, or either order's median >1.15 (candidate/stock); it is not a significance test.

## Reproduction and limits

1. Get an unmodified checkout at the exact commit above, this packet, Linux x86-64 Rust/Cargo/rustfmt 1.95.0, Python 3.11+ and the official crates.io archives in the embedded proof lock. Verify the packet with `sha256sum -c SHA256SUMS`.
2. Run the verifier in new private scratch. Repeat `--archives` if the checksum-matched `.crate` files live in multiple directories. `--timing` is optional; choose a CPU in the process's allowed affinity list for paired timing.

```sh
python3 -B proof.py --source /checkout/Proteus-core --work /private/scratch \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-archives \
  --timing --cpu 7
```

The verifier checks Git blob and SHA-256 identities, forward/reverse byte identity, exact changed paths, rustfmt, toolchain hashes and both cargo locks. It reconstructs a fresh directory source from official archive checksums and builds offline/locked in debug and release. The isolated lift compiles the actual render_causal and general replay functions, message/part renderer, row indexes, timestamps, CausalStage and physical BufReader scan body with pinned canonical DTO and complete output-field declarations. JournalEntry excludes unused hook/request/context variants; UUIDs are fixed, serde_json uses its ordinary default map, and anyhow's error alias/ensure is locally adapted for the scan. A test wrapper supplies a physical spool, invokes the certification logic, selects causal/general according to its result, and injects the late error after an observed valid row. This is not a full native Core crate linkage, strict journal validation, remote read, cache or Desktop worker. No real owner data, process RSS/PSS/peak or startup time was measured.

Native follow-up: run Core's journal source / staged_text, borrowed_parts, replay_frontier and append suites in the full pinned workspace. Then trace a cache-miss native long session and a complex/ordinary session with separate decode, render and post-render cache phases; sample per-process RSS/PSS and compare matched commits. The patch does not establish that an owner's process takes this branch.
