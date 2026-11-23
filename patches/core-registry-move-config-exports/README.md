# Core registry: move the owned config exports

Apply `source.patch` to
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
The only source change is in `crates/proteus-core/src/core/registry.rs`.

Registry construction already consumes the catalog. After its final
fallible build, it now moves the export vector into the registry instead
of cloning it. The already-owned binding strings, nested module config
and launcher handles arrive together in the same order. Worker creation,
binding validation and authority, timeouts, failure order, and subsequent
export selection are unchanged.

This reduces a transient copy, not necessarily retained bytes. Moving
can preserve spare vector capacity that cloning discarded. In the
three-export fixture reserved for 32, capacity remained 32 after the move;
the stock clone had capacity 3.

The pinned Rust 1.95 lift passed 5/5 in debug and optimized modes. It
compiles the exact registry tail, the inactive-model export selector
before any transport, and the actual binding/lookup structs and getters
with inert surrounding types. It checks existing plan/policy/workflow
and storage failures, exact schema association/description/timeout,
unchanged launcher identity and count, a single final launcher drop,
and pointer preservation for the moved vector and nested payload.

In a scoped fixture with 16 prepared exports, each with 65,536 UTF-8
bytes in an inert nested value, allocation requests fell from 219 to
11 and requested bytes from 1,073,575 to 249 in both modes. Neither
reallocated. These are allocator requests for this fixture, not
actual Serde, app startup, process memory, or whole Core validation.

To reproduce, use unpatched V4 and the pinned Rust compiler. The proof
checks source identities and exact replay/rollback, and does not invoke
Git, Cargo, any worker, or the network.

```sh
src="$CORE/crates/proteus-core/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$src/core/registry.rs" \
  --catalog "$src/core/module_catalog.rs" --exports "$src/process_adapters/config.rs" \
  --binding "$CORE/crates/proteus-module-protocol/src/binding.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
