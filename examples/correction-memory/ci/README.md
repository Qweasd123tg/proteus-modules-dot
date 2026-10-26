# Two-phase dependency admission

The initial hosted workflow performs exact Rust toolchain bootstrap, 35 pure/mocked
controller controls, `cargo generate-lockfile`, and locked/offline no-deps metadata
only. It does not run rustc on this crate, build scripts, SQLite or module tests.
The generated lock and summary are bounded retained artifacts for separate review.
Its pins must retain SDK3f, rusqlite0.33.0 with bundled SQLite/libsqlite3-sys0.31.0,
and ring0.17.14. Broader semver-selected transitive dependencies will be disclosed
in the lock, not silently treated as prevalidated.

A new second-phase commit with the reviewed lock and runtime workflow is required
for execution. This first phase cannot claim any of the69 authored tests passed.
The six own-binary wire cases and one pure framing helper remain distinct from
actual Core authorization/routing, which is outside this crate's tests.

Controller production admission:8GiB free on the target/evidence filesystem;
1200-second deadline;1GiB+128MiB sampled disk stop;4MiB each outer pipe;8MiB each
retained file;32MiB total retained artifact payload. These are sampled growth
monitors, not quotas or a sandbox. Cleanup is only of the owned unreaped group;
all-descendant settlement remains unproven. An abnormal phase ends the dedicated
job. No cleanup of caches or follow-on compile/test is included.
