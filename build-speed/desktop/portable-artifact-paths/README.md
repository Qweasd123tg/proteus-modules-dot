# Portable Cargo artifact-path correction (source-only candidate)

## Result and scope

Desktop `scripts/portable.py` previously built Core, reference module and native
with Cargo's inherited target/cache configuration, then copied guessed
`<source>/target/<profile>/<name>` paths. An external target can therefore leave
a missing artifact or copy an older default-target binary.

The candidate uses Cargo JSON `compiler-artifact.executable` for exactly these
three binaries and verifies the expected package manifest, bin target name/kind,
non-test profile, unique emitted path and existing file, plus exactly one
`build-finished` with boolean `success: true`. It accepts fresh cached
artifacts. Missing/ambiguous/malformed output, missing files or nonzero Cargo
exit fail before portable assembly. Compiler diagnostics are forwarded; Cargo
stderr remains inherited. JSON stdout is buffered until each build finishes.

The separate one-line extension invocation change sets subprocess cwd to the
extension source root. Its absolute script/bundle paths stay unchanged. At the
pinned extension revision, `package.py` builds Cargo with its own ROOT but
interprets a relative `CARGO_TARGET_DIR` against process cwd; these now agree.

**Not covered:** extension packager still guesses `target/release`. The cwd fix
does not repair arbitrary extension Cargo config target-dir or target triples.
The candidate is not an end-to-end cross-compilation fix.

## Pinned read-only evidence

- Desktop main: `f5c5c88a686b4b85c03734b6d83227ba65afb96b`
- Core main: `d48a907cec8706c3117ed8a005ec35098ecbbbe0`
- Modules main/pin: `56571639c804443dbca58e054fff8631ecb8b312`
- Extensions main/pin: `3361fc1650c4ac6f167c3e48a0fba8980a5c9038`
- Delivery main: `03d0d69780f848f564198ad82cdec4f2ff45bd81`
- Original Desktop `scripts/portable.py` Git blob:
  `280474d5f3aaf59abdc47a49d559036b4a80a567` (snapshot hash verified).

Relevant source:
[portable.py](https://github.com/Proteus-harness/Proteus-desktop/blob/f5c5c88a686b4b85c03734b6d83227ba65afb96b/scripts/portable.py#L56-L125),
[Core artifact precedent](https://github.com/Proteus-harness/Proteus-core/blob/d48a907cec8706c3117ed8a005ec35098ecbbbe0/scripts/build_module.py#L12-L33),
[extension package.py](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/3361fc1650c4ac6f167c3e48a0fba8980a5c9038/package.py#L21-L33).

## Unchanged semantics

- Default and `--no-archive`: Core/reference/native retain release.
- `--fast`: Core/reference retain release; native retains fast; no archive.
- `--debug`: Core/reference/native retain dev output; extension packager remains
  release as before.
- No Cargo.toml/profile/toolchain changes, no environment clearing or override,
  no cache deletion, no `cargo clean`, no skipped compatibility/release gate.
- Delivery is a source-only branch/draft PR in `Qweasd123tg/proteus-modules-dot`;
  upstream repositories and main are not changed. No merges or deployments.

## Verification performed

- Reusable guarded runner: `python3 validate_mocked.py`. It rejects standard
  Python process/network audit events before loading either test suite and
  requires all 26 test cases to be discovered.
- 24 stdlib mocked regression tests in `after/scripts/test_cargo_binary.py`.
- 2 extra mocked regressions against the exact pinned extension packager
  snapshot in `reference/`: relative and absolute target placement.
- Patch applies cleanly to the exact original portable snapshot.
- Tests do not run Cargo, npm, product executables, build scripts or real source
  resolution. Inert temporary files stand in for manifests and output binaries.
- No real Rust compilation, product/UI run, portable assembly, performance
  measurement or release qualification was performed.

Mock coverage includes fresh output, wrong package manifest/name/kind, test
artifacts, duplicate/missing executable, missing file/directory, paths with
spaces, relative emitted paths, inherited target environment, nonzero status,
diagnostics, malformed records, unsuccessful build-finished, profile/archive
selection and build-failure-before-assembly.

## Build speed versus runtime modules

This is a correctness prerequisite for reusing target/cache locations, **not a
measured build-speed improvement**. Native-only release iteration can already
avoid all packaging work without weakening Desktop opt3/thin-LTO/CGU1/strip:

```sh
# CWD: Desktop; component build only, not a finished portable distribution
cargo build --locked --release -p proteus-native --bin proteus-native
# CWD: Modules; reference module build only, no Desktop/Core relink
cargo build --locked --release -p proteus-reference-module --bin proteus-reference-module
# CWD: Core; existing source resolver/build helper prints the actual module path
python3 scripts/build_module.py --profile release
```

These are existing-command descriptions, not commands executed for this patch.
Independent configured process modules are loaded at runtime; their own changes
do not inherently require Desktop relink. Internal Rust crates linked into the
aggregate reference-module executable still require that executable's rebuild.
No dynamic-library or new plugin architecture is introduced.

Full portable remains a delivery checkpoint. It always stages/copies assets,
runs DCP npm ci/build/prune, builds/bundles extensions, writes notices/provenance,
and (unless omitted) archives. Cargo may reuse compiled units; it is incorrect
to call every portable invocation a full Rust recompile. DCP staging rebuilds
are distinct from Rust cache hits and need independent measurement before a
safe content-keyed cache change.
