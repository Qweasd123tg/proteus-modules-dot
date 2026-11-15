# MCP Args/Env JSON form: source-only prototype

Known [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85) text-roundtrip family, not a new finding or a deployed fix.

This package replaces the lossy form boundary with a JSON string array / string-valued object. Explicit empty values are `[]` / `{}`; decoded duplicate keys are errors. Existing profile DTOs and dependencies stay unchanged. It deliberately rejects legacy newline/KEY=VALUE input; see REPORT.md for migration, unsupported blank keys, mixed-client and UX caveats. No performance or code-size reduction is claimed.

## Apply only for further qualification

Target: `Proteus-harness/Proteus-desktop` at `7eaf70c67dabba8595d98029c875ffc3f59209ad`. Verify baseline paths against SOURCES.json / READ-VERIFICATION.json. In a separate clean checkout, run `git apply --check --whitespace=error <patch>` before `git apply --whitespace=error <patch>`; do not force mismatched hunks. DIFFSTAT.json contains expected output hashes. This delivery repository only stores the proposal, not a running client.

## Actual verification

Publisher independently verified 17 baseline SHA256/Git blob identities, the reviewed patch hash, strict check/application and eight applied-file output hashes. SOURCE-REVIEW.md records independent source review. SHA256SUMS pins the published package.

Rust compiler, cargo and rustfmt are unavailable. Ten proposed Rust tests, compilation, formatting, native UI, save/profile readback and MCP process execution were NOT RUN. No new dependency, live configuration, process, production installation or upstream repository was changed. Not production-ready. Build/native acceptance and save/readback gates in REPORT.md remain mandatory.

Only reports, source identity metadata and an inert patch are published; no raw logs, private filesystem paths, credentials or full source snapshots. Patch source context inherits the Desktop upstream licensing; this package does not relicense it.
