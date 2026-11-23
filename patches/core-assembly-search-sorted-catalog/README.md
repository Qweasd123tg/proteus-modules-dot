# Core assembly: use the already sorted catalog

Apply `source.patch` to
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
Only `crates/proteus-core/src/core/assembly/mod.rs` changes.

Assembly already owns module summaries sorted by `(slot, id)`. The
slot and hook checks now search that slice rather than allocating a
temporary tree and cloning its keys. Upper-bound search selects the
last matching row, the same result as Rust 1.95's stable BTreeMap
collection even in a synthetic duplicate case. Real catalog tuples are
unique by the textual SlotId and module ID.

The table was scratch only. Owned catalog summaries and output slots,
source attribution, configured export mapping, diagnostic text/order,
permissions, validation, and runtime construction are unchanged. This
is a pre-ready assembly change, not a startup measurement.

Rust 1.95 debug and optimized builds each passed 7/7 tests: the actual
summary sort and SlotId type, actual slot descriptors, assembly
selection and diagnostic excerpts with inert config/validation inputs,
5,120 generated lookup pairs and 1,024 generated plan pairs per mode.
The tests compare exact slot/source/diagnostic fields, the last matching
pointer, and output ownership after catalog lookup.

With 128 prepared catalog entries, the isolated assembly excerpt went
from 335 to 51 allocation requests and from 26,920 to 2,207 requested
bytes in both modes; neither reallocated. Summary creation and fixture
inputs were outside the counter. These are scoped allocator requests
in a synthetic fixture, not startup time, RSS, real Serde validation
or whole-Core runtime evidence.

To reproduce, point to unpatched V4 sources and the pinned Rust 1.95
compiler. The verifier checks all identities and exact forward/reverse
replay. It invokes neither Git nor Cargo and needs no network.

```sh
src="$CORE/crates/proteus-core/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$src/core/assembly/mod.rs" \
  --catalog "$src/core/module_catalog.rs" --types "$src/core/assembly/types.rs" \
  --exports "$src/process_adapters/config.rs" --slots "$src/core/core_slots.rs" \
  --manifest "$CORE/crates/proteus-contracts/src/domain/module_manifest.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
