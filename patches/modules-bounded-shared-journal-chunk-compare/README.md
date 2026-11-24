# Compare existing shared JSONL chunks without a second heap buffer

**Production diff: `source.patch` only.** On Modules
`331cfc20bbaf821ab07de49868426da29ebdeb64`, it replaces the full-file
`Vec` comparison in `blob_codec::store_chunk` with the existing
`io::bounded_file_eq`. The helper is already shipped for image PutBlob,
previously proposed in [#271](https://github.com/Qweasd123tg/proteus-modules-dot/pull/271).
The journal chunk caller is separate. Nothing changes in chunk names,
hashing and split points, manifests, journal records, creation of missing
chunks, or readback.

Both paths check the metadata of the opened descriptor and read until EOF
or 65,537 bytes. They keep checking after a mismatch: a limit or applicable
I/O error still takes priority over “shared blob collision”. The new helper
uses 16 KiB of stack scratch. No new metadata-length shortcut, hash-only
comparison, or additional open is introduced.

## Results

Two actual JSONL appends produce distinct parent manifests for typed
1,048,941- and 1,048,951-byte history payloads. They share physical chunks
on disk, including exact 65,536-byte matches. Stock and candidate produce
identical journal bytes, manifest bytes, ordered blob references, chunk
contents and decoded fixtures within each serialization mode. Both manifests
also match a separate full-Gear Python oracle.

| Serde JSON mode | Reused chunks / file bytes read | Stock requests / reallocations in comparisons | Candidate |
| --- | ---: | ---: | ---: |
| Default | 28 / 988,882 | 28 / 296 | 0 / 0 |
| Preserve order | 29 / 1,022,549 | 29 / 307 | 0 / 0 |

The largest **requested live heap allocation within an individual comparison**
is **131,072 → 0 bytes** in all four debug/release and map combinations.
Stock's terminal Vec capacity is measured, not inferred from the file size.
All successful matching comparisons end with zero tracked live bytes and one
validated regular descriptor. The caller's input, path, digest and manifest
allocations are outside this meter. Sequential requests are not simultaneous;
neither these totals nor the scoped peak is a claim about inclusive append
peak, allocator residency, RSS, latency, process startup or deployed hit rates.

## Verification and limits

Each profile/layout pairs 17 real-file append cases and two nonpacked
controls. They exercise exact matches, a missing chunk, a dangling or valid
symlink, a directory, empty/short/long objects, corruption at beginning/middle/
end, 65,536 and 65,537-byte boundaries, and controlled growth/truncation or
pathname replacement after opening. An error preserves the prior journal
and never publishes the new parent; a new chunk written before a later
failure still exists in both arms. One repeated serialized payload is a
raw codec/backend control for bypassing the packing branch, not a guarantee
that the service accepts re-appending the same history mutation. A rename
after open compares the old descriptor; subsequent decode detects the
new path's corruption in both arms. Arbitrary concurrent file mutations
and identical read syscall sizes are not guaranteed.

Eight separate reader-level controls substitute a scripted reader into the
pinned comparison loops. They check interruption before and after a
mismatch, late I/O overriding mismatch, an I/O error at the exact limit,
and stopping at limit+1 before a further error. These are not native disk
faults, and native file comparisons use the actual std File path.

The replay lifts the pinned JSONL recover/append bodies, used codec/Serde
payload reader and blob codec, and real I/O through durable temp-file,
fsync and rename operations. The only UUID substitution generates unique
temporary filenames locally. The locked SDK's relevant DTO declarations
are lifted; unrelated journal entry, part and optional-field types are
adapted to the text HistoryMutated fixture. The diagnostics counter is a
no-op. Comparison instrumentation observes opened descriptors and the
original Vec, and drives deterministic race controls; none of it is in the
production patch. This is not a whole-workspace/worker build, full
StorageService writer lifecycle, archive compaction run, or system benchmark.

## Replay

Stage the read-only files named in `SOURCE-PROVENANCE.json` under
`refs/modules` and `refs/sdk` at their listed commits. Provide the 36
official crate archives identified by `Cargo.lock` and the pinned Linux
x86-64 Rust 1.95.0 tools. Archives are checksum-checked against both upstream
locks. Ring also requires a local native C compiler, which is not part of the
Rust tool binary hashes. The script checks the entire product file with
rustfmt and proves ordinary forward application and exact reverse.

```sh
sha256sum -c SHA256SUMS
python3 -B proof.py --refs /path/to/refs --work /fresh/replay \
  --toolchain-bin /path/to/rust-1.95.0/bin --archives /path/to/official-crates
```

Repeat `--archives` for archives stored in different directories.
