# Core: consume decoded Replace in temporary strict recovery

The M376 strict recovery fold already transfers decoded Append messages
(#617). For a full Replace, including a changed compaction, the old
fold still deep-cloned the entire decoded replacement DTO before staging
the original bytes. Transfer the validated replacement Vec instead. The
same replacement preflight clears pending capture, validates the report,
and preserves compaction debt accounting and interruption semantics.
Active IDs are rebuilt in their original order. The recovery fold drops
its preceding canonical owner before active IDs and before the staging
observer; the original incoming record is intact during that observer.

The durable writer's borrowed path remains; it shares the same replacement
preflight and compaction completion code. Checkpoints, including their
special capture/suffix rules, remain on the prior borrowed fold. Failure
still discards the temporary state, without a callback for the rejected
record. This is not a transactional rollback API. No wire, caps, provider,
projected two-frame overlap, source, cache, authority, or renderer change.

## Evidence

Exact M376 1,100-file Core inventory strictly applies and reverses here; the
production preimage requires #617. The genuine native Semantics suites
passed 21 before and 23 after in each JSON map layout with exact M376
Contracts and locked registry releases. New tests exercise capture reset
with a formerly pending tool result (no resurrection), a real bound turn's
compaction-debt increment, interrupted-turn data preserved on an ordinary
replacement vs cleared on changed compaction, the prior history owner gone
before callback, and competing invalid report/active ID errors.

A separate native exact-source lift drives strict host ReadRecords and
render/cache publication over a fixed typed in-process SessionStorage
boundary. Each layout passes 58 existing startup fault/control fixtures,
two old-frontier fixtures and three replacement fixtures (valid changed
compaction on a second page, plain reset, and invalid report). Both arms
match final cursor/output, cache page bytes, read/write trace and error.
A rejected Replace does not stage that record or issue any cache writes.
The compacted large route had 256 earlier visible rows and a 50,000-row
single replacement record. The read adapter delivers one record per page
and checks the genuine request/response envelope and caps, so the large
record exercises the legitimate single-record exception. The original
preceding messages are released before staging in both arms (does not
assert anything about unrelated owners or allocator-retained pages).

| Strict 50k ×5 Replace, before staging | Default | preserve_order |
|---|---:|---:|
| Fresh live requested bytes, stock to candidate | 76,521,426 → 37,492,024 | 80,282,826 → 37,634,832 |
| Fresh live allocations, same moment | 117,146 → 17,027 | 117,027 → 17,094 |
| Tagged original string owners transferred | 0 → 50,000 (24,388,890 B) | 0 → 50,000 (24,388,890 B) |
| Tagged outer/nested Vec bytes transferred | 0 → 14,400,000 | 0 → 18,400,000 |

Fresh counts are actual System requests since the current fold started,
including index nodes, and may vary with map seeding. Tagged ownership
uses true allocation generations, not only returned pointer addresses.
This is one phase and a distinct Replace fixture, not the default Append
workload, process peak, PSS/RSS, startup latency, GUI or the reported
695 MiB. No measured benefit is claimed for projected state or Checkpoint.

## Replay

Extract the exact M376 Core archive to m376/ and apply the source patch
to a separate tree. Copy the resulting Semantics crate under new-semantics/
and the touched leaves under changed/. Use native-proof.tar.gz's
compile-semantics.py and build-route.py with the locked earlier release
dependency closure or recreate that closure from its verified registry
archives. Genuine Contracts inputs are proven byte-identical to composed
M376. The native lift's generate.py creates both source layouts; its
cases are controls, frontier and replace. compare.py checks the complete
JSONL output. The archive contains replay inputs and raw results, no
executable or large dependency binary.
