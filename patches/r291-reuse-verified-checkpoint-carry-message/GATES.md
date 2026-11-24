# R291 acceptance contract (frozen before native builds)

Only production delta: reuse the **already rebuilt and typed-equality-checked**
canonical message while carrying the identical captured binding across a later
checkpoint where it is neither acknowledged nor compacted. Match old priority,
input binding order/offset, current and returned history, result and error,
message/part IDs, call ID, output/error, structured content and metadata. Keep
the full exact comparison, next-state validation and proposed prefix copy. The
raw result's call ID must select the very same outer binding: mismatched raw
IDs must take the original ordinary record path, including unknown/no-op, other
binding insertion and duplicate precedence. No additional semantic/public API.

## Required native checks, each actual Serde map layout

* Positive physical strict (JournalValidationState::apply_sequenced) route:
  real initial checkpoint declares call binding, real result is captured, and
  second checkpoint carries it. Prove typed state, IDs and checkpoint digests;
  an accepted second/following use of returned state remains valid. Native
  exact lifted live no-store checkpoint should likewise prove the real ACK,
  history, revision, bindings, and untouched sink/ordering for that path.
* Test meaningful inline output, error and structured payloads at 1/4/8 MiB
  (body-only UTF-8 bytes, not wire encoding). The 4/8 MiB positive accepted
  routes in each layout must avoid at least **2 MiB of genuine requested
  allocation Layout** per carried result, and precisely one full second
  construction, not a re-encoded or less complete result. Check exact preparatory
  requested allocation counts/bytes and retained typed bytes/capacity equality.
  At actual insertion, previously verified output/error and canonical part
  backing (and structured ToolContent Vec backing when present) have the
  **same live underlying allocation generations** in the candidate. None of
  those stock generations may remain live in the corresponding stock prepared
  observation at insertion, even if an address has already been reused. The
  scoped requested-and-freed bytes/call deltas must agree; net retained bytes
  and selected capacities stay equal. Scoped full second construction can be
  checked against exact observed first construction bytes/calls, not inferred
  from request width alone. Keep generation tags/test hooks outside production.
* Ordinary record/record_at still select and construct once on accepted
  insert and honor duplicate/lost/unknown branches. Binding deletion/change,
  prefix loss, extra or changed result, canonical result mismatch or missing
  typed part, first duplicate ID (direct helper), acknowledged/compacted and
  untouched starts-with must not claim a carry saving. Check reordered pending
  bindings and distinct completion order; partial acknowledgement mixed with
  pending results and later continuation. Genuine invalid durable cases must
  reject through the exact old diagnostic/phase/order, not just comparable
  booleans. Public impossible-as-normal crafted raw call IDs: unknown result
  must make no insertion, different unrecorded binding must use its own outer
  IDs/clone, already recorded binding must give the old duplicate error.

Requested Layout scope begins just before first result construction, ends after
the old insertion or corresponding error. Allocation addresses never appear in
receipt, identity couples address and monotonic allocation generation. Realloc
is old Layout retirement plus new request. Old persisted input/retained source,
ACK serialization, unrelated prefix/map clones, active-ID checks, full operation
peaks, host malloc overhead and stack are outside this attribution. No CPU, RSS,
RAM, complete-workspace, production I/O backend, or ordinary text/startup claim.
