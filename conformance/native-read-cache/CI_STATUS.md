# Native read-cache CI candidate

The preserved SOURCE-RECEIPT.json describes the reviewed, initially unbuilt
snapshot. This branch stages it byte-for-byte for execution on an ephemeral
hosted runner. No local native-cache build or runtime pass is claimed.

The authored probe uses public Core APIs at exact
`1fc3ef223d10322815dd9290a50d045bc95402bb`, fresh owned datasets and no providers,
plugins, modules, model calls or user hooks. Controller mocks are distinct from
actual Core child-process results. Functional observations and untraced debug
measurements are reported separately; no release/production speedup is inferred.

Optional tracer availability is recorded without installation, permission
changes or an alternate tracer. Only owned child processes/threads are traced,
only openat syscalls, with 8MiB per-child-file and 120-second wall limits.
Semantic equality alone is never described as a cache hit. Missing or denied
tracing remains explicitly unavailable; cache-hit acceptance requires its actual
positive and negative trace controls.

Runtime CI results are pending at this initial staging point. A draft PR is
created only after the scoped gate is verified; no merge/deployment is requested.

The workflow additionally runs 27 separately labeled synthetic artifact-verifier
controls, then checks exact child identities, commands, results, typed values,
resource/isolation settings, source/binary stability and all three trace controls.
Completed successful openat calls must match the exact owned session paths;
failed or unrelated opens do not establish a cache hit. The original runner's
attempt counters remain retained but are not the sole hit criterion.

The 23 functional child invocations, three diagnostic traces and 18 measurement
child invocations are not a count of unique product guarantees. In particular,
controller/verifier mock tests never execute Core or a tracer. Follow the exact
commit's workflow results and PR validation description for execution outcomes;
this file preserves the source-staging boundary rather than claiming a local run.
