# Shared module runtime: release registration config before serving

Apply `source.patch` to
`Proteus-harness/Proteus-modules@331cfc20bbaf821ab07de49868426da29ebdeb64`.
The patch changes only `components/module-runtime/src/lib.rs` and
`registry.rs`.

Shared worker initialization still clones opaque config into the
registration registry, then runs registration and the schema callback
with their original inputs. Only after both complete does it drop the
registry's private copy. The original owned binding stays in
`ModuleExport`, and runtime calls continue to read that original.
Registration admission, callback and error order, registered module
ownership, schemas, permissions, and protocol are unchanged. Public
`CollectedModules::with_config`, its default, and direct
`ModuleExport::new` are unchanged.

Pinned Rust 1.95 passed 6/6 in both debug and optimized builds. The
isolated proof lifts the exact setup closure, registry code,
`ModuleExport` constructor, and locked SDK shapes. An inert SDK,
module objects, serializer values, and tool catalog avoid any real
worker, host, or provider calls. It compares registration and schema
visibility, map state for all seven registration methods, original
binding and later invocation access, rejection and duplicate errors,
schema unwind cleanup, and direct public constructor behavior.

With a synthetic 1 MiB nested text payload, both arms had 2 MiB of
tracked text alive through the schema callback. At the serve marker,
stock still had both copies; the patched arm had only the original.
That verifies the drop point in this fixture, not physical memory,
latency, or a claim that the registration clone no longer happens.
No real Serde/host process or workspace Cargo build was run.

To reproduce, supply the exact unpatched Modules sources and lock,
the locked Core SDK sources, Rust 1.95 and private scratch. The proof
validates all source hashes and exact replay and rollback. No Git,
Cargo, worker process, or network is invoked.

```sh
mr="$MODULES/components/module-runtime/src"
sdk="$CORE_SDK/crates/proteus-contracts/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --lib "$mr/lib.rs" --registry "$mr/registry.rs" \
  --exports "$mr/exports.rs" --lock "$MODULES/Cargo.lock" \
  --sdk "$sdk/process_module.rs" --binding "$sdk/contracts/process_module.rs" \
  --schema "$sdk/domain/config_schema.rs" --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
