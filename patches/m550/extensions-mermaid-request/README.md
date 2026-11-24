# Mermaid: return the original worker request as the cache key

When the extension misses the cache, the serialized Mermaid request currently
lives twice: the renderer keeps the original key and the worker channel makes a
full String clone. Send the original allocation to the IO thread and return it
with the parsed reply. This is the same JSON line, not a hash or reconstruction.
On a hit nothing changes; on errors the key is dropped, and the pool retires the
failed worker as before. Exact request bytes, ordering, source and theme limits,
reply framing, timeout, SVG checks, cache admission and teardown are unchanged.
The payload is copied across the Rust/Node process boundary as before; only the
extra Rust heap allocation and memory copy on a cache miss are eliminated.

**Base:** authenticated Extensions M350 native archive (151 inputs, Git tree
`4b1793c116d3d10f03782e6fe71fe5146c446b99`) plus exact accepted #596/#598;
one coherent ownership change in two Mermaid source files, no overlap with those
prior patches. Only source.patch is the product change. Receipt records exact
pre/post Git blobs, lock, archive and diff checksums. No dependency change and
no different map mode: native Extensions explicitly enables preserve_order,
and the new queue operates on already serialized, opaque bytes.

**Checks:** native Rust/Cargo 1.95.0 and Node >=20, original immutable lock and
vendored Pele. All 12 existing unit tests and the existing addressed-error
process test passed in both arms. The unrelated procfs lifecycle test failed
at the identical child-list assertion in this host because the per-task
children list is unavailable. The additional real-process proof uses a
transparent exec wrapper around the actual Node executable for lifecycle
observation (not a stub renderer). It checks two sessions, cache hit/miss,
theme-only change, addressed parse failure, source/request limits, restart,
last close, and EOF. Exactly three Node launches, all reaped, in each arm.
Nine ordered protocol replies total 8,828 identical bytes; SHA256
`4975a3d38f0485dc952a20083cc4a9c1a36ae60e821b85b30867e8672d7beb10`.
A separate same-process Rust unit test runs the actual vendored worker and
compares pointer/length/capacity/bytes of a 486,318-byte request across the IO
thread on successful calls on both sides of a failed call. No timing, allocator
sampling, PSS, GUI or overall app startup claim.

**Reproduce:** Linux with Rust/Cargo 1.95.0 and Node >=20 on PATH; use the
verified 27-package locked Cargo vendor. In a new scratch directory run:

    python3 proof.py --baseline /path/Extensions-M350-native-inputs.tar.gz \
      --height /path/596/source.patch --widgets /path/598/source.patch \
      --vendor /path/to/vendor --work /path/to/scratch

The separate real-process proof replaces only the host-dependent child-list
oracle; to check the original assertion on a host that supplies it, run
`cargo test --locked -p extension-mermaid-render` without the filter in your
checkout. Test-only source is not in the product diff.
