# Desktop: build one backend failure report from borrowed log lines

One production patch against exact Desktop M414, whose Desktop tree
is byte-identical to M411. The earlier source-only W17 HOLD is now
qualified by the successful serial native run. The selector is
unchanged. It is **not** the W16 log-buffer pooling/reclamation trial.

Before the change, Desktop cloned all stored diagnostic strings,
joined a temporary report, then formatted the final prefixed error.
Now it reserves the exact remaining output size from borrowed lines
and writes the existing status prefix and lines into one report.
The raw reader, readiness, log retention/redaction, lifecycle and
process ownership are byte-identical.

The harness compiles the exact Linux `Backend` and the original
client-common origin guard running with its pinned URL parser. It
starts a real synthetic child via the production `Backend::launch`,
through its own stdout/stderr pipes, and measures `exit_report`
after the process and readers finish. Both Rust JSON map modes
passed all four tests in both arms. The test uses generated data only.

| Scope: actual large report (5,626,766 identical bytes) | Stock | Candidate |
| --- | ---: | ---: |
| Allocator requests during the report | 63 | 2 |
| Cumulative requested bytes | 16,881,651 | 5,626,800 |
| Peak added bytes | 11,254,851 | 5,626,766 |
| Final returned allocation | 5,626,766 | 5,626,766 |

The tiny report retains an identical 882 bytes (peak 3,083→882);
the empty report allocation is unchanged. The native tests check
startup failure before readiness, a normal ready handshake and
post-exit report, old 60-line ordering, invalid UTF-8, redaction,
empty lines, and rejection of invalid readiness origins. The actual
90-second timeout was not waited out; it uses the same verified
report builder and unchanged message prefix, checked in source.

These measurements apply only to startup failure or an owned
backend that has exited. They do not measure read scratch, latency,
system RSS/PSS, the full Desktop or routine history startup.

Exact #651 ordering and inverse, all input hashes, receipt/binary
hashes captured before cache cleanup, and both guarded/native
results are included. The separate source-capsule replay passed
without starting a second build. No graphics/Node, auth, system or
remote changes.

```sh
sha256sum -c SHA256SUMS
python3 verify.py                       # source replay; no compile
python3 verify.py --vendor /path/to/vendor  # optional Linux native replay
```
