# Project check: borrow the bounded diagnostic output

Apply `source.patch` to
`Proteus-harness/Proteus-modules@331cfc20bbaf821ab07de49868426da29ebdeb64`.
Only `workflow/coding-workflow/src/project_check.rs` changes.

The failed-check explanation prompt borrows the UTF-8 prefix and static
truncation marker instead of copying them into a temporary String.
The header text is unchanged. The final String reserves once for the
combined tail, then appends both pieces. This also avoids a second
geometric growth for a tiny marker at the production truncation boundary.
The limit is still 12,000 Unicode scalars. Prompt bytes, project
selection, commands, model calls, permissions, and public behavior are
unchanged.

The pinned Rust 1.95 lift passed 12/12 tests in both debug and optimized
modes, including the original pure fixtures in both arms and 4,096
generated comparisons per mode. The proof uses exact prompt/bounding,
project and Git-state functions with inert DTO fields checked against
the locked SDK. It compares full prompt bytes, Unicode boundaries,
missing/empty errors, existing markers, zero and `usize::MAX` limits,
and empty/tiny final capacities.

For 12,001 four-byte scalars, the bounding helper went from 1 allocation
and 3 reallocations to none. The full prompt went from 2 allocations and
4 reallocations to 1 of each; summed requested bytes were 228,382 →
48,382. The returned String's capacity stayed 48,182 bytes in both arms.
These are scoped allocator requests, not live or peak memory, latency,
host/provider or whole-workspace results. No project command, worker,
model call, or actual Cargo workspace was run.

To reproduce, use the exact unpatched Modules sources and lock, the
locked Core SDK sources, pinned Rust 1.95, and an existing private
scratch directory. The proof validates all source identities and exact
forward/reverse patch application.

```sh
sdk="$CORE_SDK/crates/proteus-contracts/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$MODULES/workflow/coding-workflow/src/project_check.rs" \
  --lock "$MODULES/Cargo.lock" --sdk "$sdk/process_module.rs" \
  --task "$sdk/domain/task.rs" --tool "$sdk/domain/tool.rs" \
  --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
