# Typed Frontmatter comparison — design, runtime pending

## Scope

An authored, standalone comparison runner for baseline `serde_yaml 0.9.34+deprecated`
and **at most two** registry candidates: `yaml_serde 0.10.7` and
`serde-saphyr 2.0.0`. The exact versions are now locked and their downloaded official registry archive
checksums independently match Cargo.lock (`SOURCE_PINS.json`). Candidate APIs and
error variants were inspected read-only; runtime results remain pending. Neither a newer release nor a green parse establishes that a
replacement is safer or a drop-in.

No original portable module source changes. `src/frozen/{config,document}.rs` are
byte-identical copies of the accepted R5 files, including its actual typed
`Frontmatter`, custom metadata visitor and module semantic checks. The runner will
compile these as modules, not redefine a relaxed test struct. Existing direct
dependency versions match R5's lock. This is an exact source projection, **not an
execution of the complete portable module or Core**.

## Observation paths

- Baseline typed decode into the frozen `Frontmatter`.
- Baseline unchanged module `document::parse` after wrapping authored YAML in the
  exact module fences/body; this additionally exercises semantic/raw/expanded
  limits and is reported separately from parser acceptance.
- Each candidate typed decode into that same type, preserving full output fields
  or its actual rejection. No generic YAML Value intermediate or normalization.
- Candidate budget probes only where a verified API supports the exact target
  and entry point. Unsupported budgets are explicit gaps, not passing tests.

Each child receives only fixed case/parser/budget identifiers; corpus bytes are
embedded/read from this authored package, never commands or user filesystem paths.
The controller uses a fresh output directory, cleared environment/empty HOME,
strict result parsing, exact matrix coverage, per-child timeout and pipe caps.
It records pre/post source and binary identities. Children execute no shell,
network, model, upstream tests, foreign hook or include/property resolver.

## Comparison policy

The 38-case corpus contains ordinary positives, ambiguous/rejected syntax and exact
raw/key-count/character/expanded boundaries. Record full field values, observed
serialization length, parser errors and module errors separately. Differences
must remain visible, including cases both reject for different reasons. The
probe is observational: it may pass its coverage/integrity gate while reporting
incompatibilities. That is **not migration acceptance**.

Budget controls always run the same valid typed document with a permissive setting
that succeeds and a restrictive setting that fails with the intended budget
category. Invalid nested String input is never used to claim a depth-budget hit.
Reader-byte controls are supplementary because R5 currently parses strings.
Comment-retention budgets do not imply raw-input containment when emission is off.
No attacker-scale payload or upstream proof-of-concept is needed; maximum authored
raw YAML is 16,385 bytes. Budget API fields/error variants must be read from the
checksum-verified candidate source before implementation.

## Rejected shortcuts

No in-place parser replacement, version-only safety claim, generic Value substitute,
library-default merge/bool semantics silently treated as compatible, automatic
include/env loader, unbounded fuzzing, huge aliases, benchmark/speedup claim, or
upstream suite execution. A later migration still requires the existing 29
behavior cases, wire case and actual-Core pair gate plus explicit decisions on
every semantic difference.

## Current state

Corpus JSON/hash consistency and exact registry archive checks passed; YAML parser
execution count remains **0**.
Four typed observation paths and seven separate envelope controls are authored.
Pinned-source budget paths are now authored for seven saphyr controls plus the
comment-emission non-guarantee. The controller/gate is authored and has passed 35 distinct helper controls (pure
verification, tiny authored Python children, mocked Cargo guards and synthetic
log checks); these are not YAML parser results. Final independent source review
is pending. No Rust compilation or parser execution has occurred.
Core skill pairing takes precedence once its separate experimental CI publication
authorization is resolved; the corrected standalone base already passed CI.
