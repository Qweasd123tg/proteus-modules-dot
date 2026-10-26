# Experimental CI gate

This authored workflow starts with no accepted Rust runtime result. It tests only
this supplied-snapshot consumer; not AppServer, actual Core transport, provider
requests, prices or audited billing. Thirty-one projection tests and six own-stdin
executable tests are distinct from Python helper and supervisor controls.

The supervisor is adapted from reviewed resource-envelope v1, changing only the
profile map to `usage-attribution: 1800` seconds. Its production admission needs
8 GiB free on the shared target/evidence filesystem; it samples disk and artifact
growth, stopping below 1 GiB +128 MiB. These are monitors, not enforced quotas or
a sandbox. Each pipe is capped at 4 MiB; each retained file at 8 MiB and artifacts
at 32 MiB. On abnormal execution the job ends; there is no follow-on test retry.
TERM/KILL applies only to the owned unreaped process group. Whole-descendant
settlement remains unproved, including any process that changes group.

Six hosted live controls run before Cargo fetch/tests: ready success, nonzero,
timeout, output overflow, an exited leader with one same-group child retaining
pipes, and an injected wait-adapter failure with a real child. They use a 4 KiB
pipe cap and 0.5-second clock. The last control is fault injection, **not a natural
kernel reap failure**; it separately reconciles that exact child. All fixtures
have an independent eight-second alarm (including the one forked child).
They do not establish general process cleanup or production startup/Cargo behavior.

The stage installs exact Rust1.95.0 minimal+rustfmt, records versions, runs pure
controller/validator controls and the six live controls, checks formatting,
fetches with the unchanged lock, then runs offline locked projection and stdio
targets. All commands record argv and return codes. Exact names, target summaries,
no ignored/filtered results, typed fixture equality and fixed fixture arithmetic
must pass. Separate fixture/null/invalid executable outputs and the binary hash
are retained. Source hashes are captured before and after. Failed or incomplete
artifacts are evidence of failure, never a pass; source-only review is not runtime
acceptance. No upstream suites, module installer, merge or deployment is included.
