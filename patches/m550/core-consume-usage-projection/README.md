# Core: move temporary model-usage receipts into a cold validated read

One coherent source change, two files. `RemoteValidatedRead::validate_snapshot`
owns a fold that will never be used again. At the existing publication site,
move its requests into the result instead of cloning all entries and owned
model/provider/reasoning strings. Consume that exact local only after the
complete existing scan, validation, display staging and revision gate. Keep
the borrowed method unchanged for all resident or reused projections. Do not
change live workers, Modules' independent SDK pin, or projected fast-path
input. A zero-model session has nothing to save.

An owned Vec has at most the retained length after converting through a
boxed slice, so this does not trade transient copies for slack in resident
output. At tight capacity the array pointer survives. At loose capacity a
shrink may move/reallocate the array; nested strings are moved either way.
No number is claimed for overall RAM, allocator retention, CPU or cold latency.

Proof uses native frozen M362 Semantics + whole pinned Contracts, plus exact
before/after Core function body from the frozen source, transplanted only
for typed storage records, CompareSnapshots result and display collection at
the I/O boundary. Tests cover exact serialized output (including revised
metadata), original borrowed behavior, 0/1/2/5/31/32/33/256/1,025 exchanges,
both geometric and explicit 4,096-slot slack, tight capacity, all five usage
statuses, completed counters, repeated equal prefixes, and injected final
scan failure, final sequence error and revised-history mismatch. Pointer
equality is checked for each provider, model and reasoning field, and for
nonempty tight vector allocation. Pending/canceled/timeout validation uses
the real journal validator, no dummy projection.

Reproduce in the baseline workspace with `python3 -B stage.py`, then
`python3 -B run.py`; these verify exact historical archive, materialize a
projected locked native workspace and keep all supplied fixture source out of
`source.patch`. `source-gate.json` proves forward and inverse on exact M362;
`native-receipt.json` is the scoped test outcome. Whole native Core and the
GUI were not run; the storage scan boundary is expressly not claimed.
