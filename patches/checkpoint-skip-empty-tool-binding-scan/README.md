# Checkpoint: skip a full-history scan when no tool-result bindings exist

The coding workflow still checks for a history update and inserts any new
tool-call bindings before constructing its checkpoint. When its binding
map is empty, produce the same empty binding list without walking
persistent history. With any binding present, keep the existing
conversation-ordered scan, including duplicate or missing matches.
Checkpoint acceptance, preparation target, validation, and ACK are
unchanged. The history update itself is not skipped.

Target: Modules 331cfc20bbaf821ab07de49868426da29ebdeb64, one file.
Exact predecessor already includes #357, which modifies another helper.

Check the patch and run a standalone source-bound Rust 1.95.0 proof:

```sh
sha256sum -c SHA256SUMS
python3 proof.py --stock /path/to/scaffold.rs \
  --rustc /absolute/path/to/rustc --work-dir /path/to/private-scratch
```

Two paired tests passed in both debug and optimized builds, including
7,000 generated history/map/ACK combinations and the new-call insertion
boundary. In the exact lifted checkpoint with an instrumented fixture of
125,000 rows, the binding scan visited 125,000 rows before and none after,
with the same inert checkpoint payload. This covers the scan only, not
real host/store integration, native Cargo, timing, startup or app memory.
