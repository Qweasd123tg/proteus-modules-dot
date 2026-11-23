# Core assembly: borrow configured export ownership

Apply `source.patch` to
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
Only `crates/proteus-core/src/core/assembly/mod.rs` changes.

The temporary configured-export map now borrows both tuple keys and
component owner names. Only the owner selected for a slot is copied to
the final plan. Literal key comparison, component iteration order,
last-owner duplicate behavior, diagnostics, validation, and authority
are unchanged.

The stock patch is independent. For a tree with either this patch or
#547 already applied, reproduce the corresponding continuation below.
The historical #547 patch contains the old export-helper signature
as context; do not blindly apply it after this patch. The proof pins
both source patches and all preimages. It adjusts only the context
signature and blob header for #547 after R246, or the header and line
coordinates for R246 after #547. It verifies both orders produce
exact Git blob `4357b97d7673e0a20df89ce63486d2119a8831ff` and reverse
exactly. No fuzzy merge or context bypass is used.

Rust 1.95 debug and optimized each passed 9/9 tests on the exact
standalone and composed selection blocks. The fixture includes the
real catalog summary order, slot descriptors, configured export
iterator, and 4,096 generated four-arm cases per mode. It compares
owned plan fields, raw key equality, diagnostics and retained config,
using inert plan inputs without runtime assembly or worker startup.

With 128 prepared exports, the scoped assembly excerpt made these
allocator requests in both modes. No arm reallocated.

| Pair | Allocations | Bytes requested |
| --- | ---: | ---: |
| Stock → R246 | 709 → 323 | 48,843 → 38,160 |
| #547 → composed | 437 → 51 | 24,376 → 13,693 |

Inputs were prepared outside the counter. These are scoped requests,
not startup time, RSS, native Cargo, real Serde, or provider evidence.

To reproduce, use unpatched pinned V4 files and the exact delivered
#547 `source.patch` with SHA-256
`2addc68ecfe3a1c0dd0c191a8ccc8ac22e11d70c9d5ff9813f4b4fefffd97fcb`.
Omit `--emit-continuations` to only verify. If supplied, its destination
must not yet exist. It creates only the named patch files and their
checksums without touching source code.

```sh
src="$CORE/crates/proteus-core/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$src/core/assembly/mod.rs" --app "$src/core/config.rs" \
  --catalog "$src/core/module_catalog.rs" --types "$src/core/assembly/types.rs" \
  --exports "$src/process_adapters/config.rs" --slots "$src/core/core_slots.rs" \
  --manifest "$CORE/crates/proteus-contracts/src/domain/module_manifest.rs" \
  --pr547 "$PR547_SOURCE_PATCH" --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH" \
  --emit-continuations "$PRIVATE_SCRATCH/verified-continuations"
```
