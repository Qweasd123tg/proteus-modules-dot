# Storage ETag: skip sorting maps already in canonical key order

`OrderedValue` previously copied references for every nonempty object into a
Vec and sorted them. Directly emit a map whose existing key order is already
lexicographic, as with the default serde_json feature mode, when it has up to
32 keys of at most 128 UTF-8 bytes each. Independently
sort out-of-order objects and preserve the recursive handling of mixed nested
maps. No reliance on a transitive build feature or map implementation; JSON
and ETag bytes, cache format, serializer and validation are unchanged.
The patch is anchored to the exact #600 postimage and must be applied after it.

Compile both exact production functions side by side in native release mode.
4,116 values per feature mode matched independent sorted JSON+SHA exactly,
including lexically adjacent, non-ASCII and reversed keys, NUL and escaped
Unicode, empty maps, scalar 1-MiB outlier, deep nested mixed maps, and both
sorted and reverse-inserted 50-row pages. The alloc meter surrounds each real
public call. Each eligible nonempty map already in key order removed exactly one
temporary reference Vec allocation. The sorted 50-row page fell from 101 to
1 allocations, minus 6,400 gross requested bytes in both modes, while the
reverse-inserted nested ordered-map page correctly stayed at 101 allocations.
No reallocations in either arm. On an insertion-ordered map with 32 keys and
its only inversion at the last pair, the pre-check adds 31 lexicographic
comparisons of up to 128 bytes each before the unchanged old sort. More than
32 keys skip the comparison pass completely; if a long key is encountered
inside an eligible count, its length check aborts before comparing that key.
Pinned release thread CPU, 12 alternating pairs per case: the sorted page
uses about 9.3% less CPU in default maps and 10.1% less in preserve_order.
The reverse page uses about 10.3% less on default maps (sorted by the map) and
1.7% more in preserve_order. The bound's deliberately near-worst 32×128
late-inversion case used 2.0% more in preserve_order (6.67→6.83 μs in marginal
medians); both larger 4,096-key late-inversion cases stayed within 0.5%
there and add no key comparisons. These are microbenchmark ratios, not
end-to-end startup or PSS/RSS measurements.

Replay the exact projected locked proof by placing the #600 source under
before/value_hash.rs and this patch's result under after/value_hash.rs.
In proof/, rename native-proof.rs, proof-Cargo.toml and proof-Cargo.lock
to main.rs, Cargo.toml and Cargo.lock, and timing-proof.rs as timing.rs.
Run `cargo run --bin ordered-etag-proof --release --locked` and
repeat with `--features preserve_order`. Actual Contracts tests separately
run under both map modes, filtered to `contracts::session_storage::` (10/10 each).
For timing, pin a free Linux CPU and run `cargo run --release --locked --bin
etag-timing` with and without preserve_order on the same host.
