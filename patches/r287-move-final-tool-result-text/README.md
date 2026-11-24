# Move tight selected tool result text into noncausal full replay rows

The last scan of the full noncausal renderer already owns each decoded JournalRecord. Previously its ToolResultRecorded branch borrowed the result and cloned the selected String into the output row. The patch moves an already tightly sized, nonempty winning raw error or output after the same live/lineage/visible-call and seen-result checks. It borrows the rest of the original record. The original text_or_status() still supplies the exact behavior for loose raw Strings, structured content and status fallback. Empty versus whitespace is unchanged: a nonempty error is checked first, then nonempty raw output. The flag for ok still controls status independently.

Status creation, tool-row lookup/add, metadata cloning, terminal decoding, timestamps and subagent binding stay on shared/unchanged code. No storage, contract, canonical journal representation or cache format change. The previous borrowed paths (causal replay, effect-only results, embedded results, append) remain borrowed. Discovery, reset frontier, rendering and durable validation occur in their original order; no hidden or duplicate final callback is moved. This is not a text-only-session or warm-cache memory improvement.

Production is exactly source.patch against Core b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14, with postimages transcript.rs 960725ce4bb63a3d03b8d39fc9ee68627054d9e5, transcript/journal.rs deb36066a7216312828a221516df4b58025ab4f3, transcript/journal/source.rs f1b407ba8b82daae83d85a59912f9395265910ff.

## Exact measurement boundary

Pinned native Linux x86-64 release in both Serde layouts. The fixture reaches the exact noncausal final render pass through the real validated projected and strict-fallback snapshot paths and physical spool; direct typed and explicitly adversarial renderer-only routes are separate controls. Only the test storage I/O boundary is substituted. The allocator ledger follows the original selected base address **and allocation generation** from a decoded record before gating into the actual rendered row. It checks again after the source callback drops the input record. Address reuse does not count as a surviving or moved generation.

The requested-Layout ledger observes alloc/alloc_zeroed, realloc as old-size free plus new-size alloc, and free events in the accepted appender and whole final record callback. Test-probe bookkeeping is excluded. This measures an avoided copy of one String, not RSS/PSS, wire/network bytes, end-to-end or process peak, tool execution, large-output release time, host latency, or Desktop startup. It does not remove other storage, canonical or metadata copies.

## First observed result

Both locked layouts passed 94 paired typed-store route cases and five separately identified renderer-only adversarial cases. There were 165 final-record pairs observed in each layout. Genuine physical projected and strict-fallback results agreed for tight ASCII raw output and tight escaped UTF-8 raw error, at 1, 4 and 8 MiB. A third, unstaged typed path corroborated those qualified moves.

| Qualified raw String | Requested copy eliminated per accepted row | Allocation count reduction |
|---|---:|---:|
| 1 MiB calibration | 1,048,576 B | 1 |
| 4 MiB | 4,194,304 B | 1 |
| 8 MiB | 8,388,608 B | 1 |

For the actual 8 MiB staged error, default accepted-append allocation traffic was 8,390,686 B / 19 allocations in stock and 2,078 B / 18 in the candidate. In preserve_order it was 8,389,962 B / 22 and 1,354 B / 21 respectively. The remaining smaller allocations are not attributed to savings. At callback exit the original winning raw generation is alive in the candidate row; stock freed that input generation and its distinct output copy remained. The exact result content, output and metadata order/capacities, status, dates, tool-row creation, terminal/subagent cases and cache reads remain equal. Whole callback allocations and frees confirm the same single-copy difference.

Loose raw input, a loose winning error with a tight masked output, empty/reserved error, whitespace masking, structured text/JSON/image/binary/status fallback and protected borrowed/general routes were checked separately. The original routes for the nonqualifying cases have matched scoped allocation traffic. Direct controls exercise hidden/wrong-root/live/detached and repeated final records, known-final-over-effect priority, reset-frontier fallback row and late-scan errors. These adversarial controls are not presented as accepted durable records; a duplicate store record was separately rejected before rendering. Faulted cache save and source/physical staging faults preserve original errors, successful row use or absence of publication as appropriate. Overall process peak or throughput has not been measured.

GATES.md defines the predeclared boundaries. The original raw JSONL receipts and independent checks are in this packet; route-scope.md states exact fixture vs production boundaries. The source-only patch was separately applied/reversed in strict combinations with #569, #577, #574 and #588; no combined runtime gain is asserted. The portable verification staged 161 pinned Core files and 152 locked registry archives with 8,573 members and exact generated source. Replay locally with python3 proof.py --core CORE --archives ARCHIVES --rust-bin RUST_BIN --work NEW_EMPTY_DIR --action run. The portable recipe was staged; the recorded native executions used the verified shared offline build lane. No deployment or external writes.

## Raw receipt transport

The original JSONL receipts are stored as Base64-wrapped gzip. Decode them before running the receipt checkers directly:

```sh
for mode in default preserve_order; do
  base64 -d "$mode.jsonl.gz.b64" | gzip -dc > "$mode.jsonl"
done
sha256sum -c RAW-SHA256SUMS
```
