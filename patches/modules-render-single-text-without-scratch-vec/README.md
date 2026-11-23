# Workflow output: skip the collector for one Text part

Apply `source.patch` to
`Proteus-harness/Proteus-modules@331cfc20bbaf821ab07de49868426da29ebdeb64`.
Only `workflow/coding-workflow/src/output_text.rs::message_text` changes.

When exactly one Text part is present, the result is copied straight
into its final String, without a temporary vector. Zero Text parts
still produce the placeholder; a single empty Text does the same.
Whitespace is not trimmed, and multiple Text parts still use the
same newline join, including separators around empty fields.

The existing #268 fallback and its tests are already in the pinned
source. Do not reapply #268. The fallback implementation and
tool-result lookup are byte-identical to stock, including the behavior
when actual Text equals the literal placeholder.

The complete source module was lifted into paired Rust 1.95 debug and
optimized tests with inert DTOs checked against the locked SDK. Each
mode passed 16/16 tests, including five existing output/fallback cases
per arm and 4,096 generated pairs. For 381 multi-part cases with 2–128
recognized Text parts, both modes matched each allocation and
reallocation request, bytes requested, and final String capacity.

On an 8 KiB single Text fixture, allocations fell from 2 to 1,
requested bytes from 8,256 to 8,192, and the returned capacity stayed
8,192 bytes. Neither arm reallocated. These are scoped allocator
requests, not elapsed time, process memory, or a full workspace test.
No live provider, host, worker or actual Serde/Cargo was used.

To reproduce, supply the exact unpatched Modules sources and lock,
the locked Core SDK sources, pinned Rust 1.95, and private scratch.
The script checks file identities and exact forward/reverse replay.

```sh
code="$MODULES/workflow/coding-workflow/src"
sdk="$CORE_SDK/crates/proteus-contracts/src"
sha256sum -c SHA256SUMS
python3 -B proof.py --stock "$code/output_text.rs" --helpers "$code/tests/output_helpers.rs" \
  --lock "$MODULES/Cargo.lock" --content "$sdk/model_standard/content_part.rs" \
  --tool "$sdk/domain/tool.rs" --rustc "$RUSTC_195" --work "$PRIVATE_SCRATCH"
```
