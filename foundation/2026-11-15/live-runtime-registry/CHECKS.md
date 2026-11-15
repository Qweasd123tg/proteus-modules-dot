# Actual checks and limits

These checks are artifact/source checks, not behavioral tests.

- Fresh baseline refs checked: Desktop 7eaf70c, Extensions f82b3ad, delivery 41e13ef (#147).
- 11 Desktop source/doc blobs verified against pinned recursive tree; see SOURCE-BLOBS.tsv.
- Historical report exact blob 2bd7d28d4ae40589efafa4ff2d3e24a554abd795.
- GitHub code search Runtimes: functional maps/consumers in declarative/mod.rs and runtime/invalidation.rs; document retarget uses collector. Other hits were source documentation/comments or functional host/runtime scope references.
- Runtime::new search: one production factory in declarative/mod.rs; direct test constructions in runtime/commands.rs (inside cfg(test)), runtime/documents.rs (inside cfg(test)), content/tests.rs (parent cfg(test) mod declaration). Search is indexed source coverage, not an exhaustive runtime guarantee.
- Forward git apply check with whitespace=error-all: exit 0.
- Strict patch --batch --fuzz=0 -p1: exit 0, three files.
- Reverse git apply check with whitespace=error-all: exit 0.
- Three candidate/application byte comparisons: equal.
- Text diff measurement: production +33/-67; test-only module 175 lines, six proposed tests. Old tuple-only test replaced; existing unmounted generation test retained.
- Independent review: source-only, no production blockers; test macro qualification resolved.
- cargo/rustc PATH checks returned no executable. All Rust tests NOT COMPILED / NOT RUN. No rustfmt run.
- No Python behavioral substitute, extension/native executable, builder, installation, provider call, live project mutation, or security experiment.

Apply checks are not compile checks. The proposed tests do not establish actual object-release timing or factory registration by execution. Native fanout/reload/rehost behavior and composition remain unverified.
