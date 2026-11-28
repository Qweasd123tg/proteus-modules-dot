# Give Modules conformance the artifact report from its own build

**Apply only one patch:**
- `source.patch` for stock Modules `7274147162cb226f05df13a52b4a271fa5619313`.
- `source-after-stack.patch` for the already stacked Modules tree `6d774f1bd37ba6b1bbb97322bb000c4382755c04` (#945, #954, #956).

Check `sha256sum -c SHA256SUMS` and `git apply --check` against the intended tree first.

The conformance runner now asks the packager for a report of the artifacts accepted in this invocation. It keeps the report in a private temporary directory until the tests return. Obsolete package names in the durable reuse index no longer become conformance fixtures. The durable index and the established `--print-artifacts` / `--no-build` paths keep their behavior. The report isolates metadata, not binaries in a shared Cargo target or a damaged durable index.

Verified with a stale record in the durable index, ordinary installed package record fields, an actual selected storage build, both storage dialects' initialization, no-Cargo reuse and focused packaging and runner tests. No whole reference conformance run, distributed package change, actual agent/provider/tool run, or deployment.
