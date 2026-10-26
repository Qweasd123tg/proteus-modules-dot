# Typed Frontmatter parser comparison — Rust runtime pending

An observational migration probe, **not a parser replacement**. It compares the
portable module's exact shallow typed target using:

| Parser | Exact registry version | Role |
|---|---|---|
| `serde_yaml` | `0.9.34+deprecated` | Frozen baseline |
| `yaml_serde` | `0.10.7` | Candidate typed compatibility |
| `serde-saphyr` | `2.0.0` | Candidate typed compatibility and explicit budget controls |

All three archive checksums were independently matched to `Cargo.lock` after a
source-only fetch. Exact source/VCS pins and inspected API files are recorded in
`SOURCE_PINS.json`. Registry/version identity is not a security or maintenance
guarantee. No Rust compilation or YAML parser execution has occurred yet.

## Real target, separate observations

`src/frozen/config.rs` and `document.rs` are byte-identical R5 source copies,
including its public `Frontmatter`, duplicate/64-key custom metadata visitor and
module semantic checks. They are not a relaxed test struct or generic YAML Value.
`FROZEN_BASELINE.json` fixes their hashes; direct dependency versions match R5's
lock. This source projection does not execute the complete portable module/Core.
The original module remains untouched.

The planned native run has **174 separately captured child invocations**, not
174 ordinary success assertions or upstream tests:

- 38 authored YAML cases × four paths = **152 typed/module observations**:
  baseline typed decode, baseline unchanged module parse, and both candidates'
  typed decode. Full fields or real rejection diagnostics are retained.
- **Seven separate module-envelope controls** establish LF/CRLF, body trimming,
  internal body markers, closing marker at EOF and precise malformed-fence errors.
- **15 budget observations** establish seven same-input permissive/restrictive
  pairs plus the comment-emission-disabled non-guarantee.

The corpus distinguishes duplicate known and metadata fields, scalar coercion,
null/missing values, tags, aliases, merge keys, multiline/Unicode behavior, invalid
shallow shapes and exact raw/expanded/character/key-count boundaries. The maximum
raw YAML is 16,385 bytes. No large resource bomb or upstream exploit runs.

Actual Rust serialized field-byte counts must match the corpus's predicted
16,383/16,384/16,385-byte cases **before** the module's expanded-limit result is
interpreted. Raw-limit cases use comment padding to hold typed fields fixed.
An invalid nested String shape never substitutes for a valid budget positive.

## Defaults, differences and budget limits

Candidate compatibility observations use library defaults and record them. Saphyr
2.0.0 defaults include merge expansion, non-strict booleans and emitted comments;
these are not silently changed to make comparisons green. Both rejection and
field differences remain visible. Two parsers rejecting the same case are **not
automatically considered equivalent**.

Saphyr budget pairs use its exact typed API and error variants for depth, nodes,
events, scalar bytes, alias count and retained comments. Reader input bytes use
`from_reader_with_options` over an in-memory Cursor and require the exact
`IOError/FileTooLarge` path. They are not a from-string byte-limit claim.
Every permissive control must preserve fields from the same valid typed input;
every restrictive control must hit its intended typed error, not just any error.

Disabling comment emission intentionally leaves the comment-heavy input accepted
with zero retained-comment bytes even when that retained budget is tight. This
is a documented accounting boundary, not proof of bounded input-processing time.
Callbacks and counters are retained; reader failure callback availability is
reported separately from its typed I/O limit error.

The baseline and yaml_serde adapters expose no adjustable counters in this probe.
That gap is explicit, not a passing budget check or a claim that those libraries
have no protections: their source includes fixed recursion/alias checks.

Saphyr is built with **only `deserialize` and `comments`**, with default features
disabled. The dependency gate rejects unexpected features. No include, filesystem
include, property/environment resolver, robotics extension, model or hook is
enabled. Include/property-looking strings are ordinary authored test data.

## Gate and run

From this package directory, with Rust 1.95.0:

```sh
bash ci/run.sh
```

The gate requires a fresh output directory, frozen source set, exact resolved
versions/features, formatter, locked fetch/offline build, exact 159 semantic/
envelope observations and 15 budget observations, unchanged source/binary hashes,
and unchanged empty child HOME/workspace/temp directories. It executes only our
binary and helper controls, never upstream parser suites. Fetch may use the
network; child parsing is in-memory and has no configured network operation.

Cargo fetch/build use the coordinated builder’s sampled 1 GiB reserve plus
128 MiB stop margin, polling every 0.1 seconds and stopping their owned process
group on threshold/deadline. No data is deleted; this is not a hard OS disk quota.
The workflow uploads evidence only when this invocation created a fresh results
leaf and recorded its input hashes; a rejected stale leaf is never uploaded.

Each child has a five-second deadline, 256 KiB per captured pipe and a 128 KiB
emitted-result cap. The controller runs children sequentially and checks a 1 GiB
plus 1 MiB disk reserve. On failure it retains evidence and attempts bounded direct
child/group cleanup. This is trusted-process testing, not OS sandbox or arbitrary
descendant-settlement proof. Durations are diagnostic, not parser benchmarks.

The gate also runs **20 synthetic verifier controls**, **four tiny authored Python
child-capture controls**, **seven mocked Cargo-guard controls**, and **four synthetic
helper-log controls**. It requires every exact helper name and one clean summary
per phase, with no skipped/failed case. These 35 helper controls do not establish
YAML parsing or budget enforcement. A successful native gate means complete,
internally consistent observations and intended controls; it may still report
incompatibilities. `migration_acceptance` deliberately remains `not_granted`.

The proposed workflow is `ci/check-parser-compat.yml` for a future
`conformance/parser-compat/` publication. No remote publication/CI has been
authorized or performed for this package. See `VALIDATION.md` for current status.

## Migration decision remains separate

A maintained parser may be worth evaluating without being a drop-in. Any real
module revision requires explicit decisions on every semantic difference, all
existing 29 behavior tests and wire proof, and the separately scoped actual-Core
pair gate. This package makes no full-module, Core, dependency-audit, RSS/CPU,
Windows/macOS or general YAML-compatibility claim.
