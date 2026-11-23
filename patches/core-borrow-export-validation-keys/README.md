# Core component shape checks: borrow duplicate keys

Apply `source.patch` to
`Proteus-harness/Proteus-core@b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14`.
Only `crates/proteus-core/src/core/module_catalog/components.rs` changes.

The temporary duplicate-export set now borrows the slot and module ID
from the same immutable config instead of cloning the two strings.
The existing tuple order and exact text comparison stay the same.
Component shape, sandbox and transport checks, timeouts, authority
checks, launcher creation and first-error order are unchanged.

Rust 1.95 passed 6/6 tests both in debug and optimized modes, including
4,096 generated pairs per mode. The paired lift uses the unchanged
actual shape, sandbox, and transport validators, with Serde annotations
and the anyhow error wrapper adapted for standalone Rust. It checks
literal keys, exact first failure, timeout and frame bounds, the
host-owned frame setting, and restricted sandbox shape. It never
grants access, opens paths, or launches a component.

On 128 shape-valid synthetic exports, the scoped checks requested
280 → 24 allocations and 14,792 → 8,152 total bytes; both made
two reallocation requests. These are allocator requests in a test
fixture, not retained memory, startup time, real Serde, or a full Core
test.

To reproduce on the pinned compiler, provide unpatched sources and
private scratch. The proof verifies sources and reverses the patch
exactly. It invokes no Git, Cargo, or component process.

```sh
src="$CORE/crates/proteus-core/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$src/core/module_catalog/components.rs" \
  --app "$src/core/config.rs" --exports "$src/process_adapters/config.rs" \
  --sandbox "$CORE/crates/proteus-contracts/src/domain/process_sandbox.rs" \
  --transport "$CORE/crates/proteus-module-protocol/src/v3/transport_config.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
