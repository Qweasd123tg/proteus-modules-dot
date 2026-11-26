# Batch fixed blob metadata before hashing

Keep the BTreeMap ordering, raw path bytes, length prefix, field widths and
little-endian representation. Concatenate the six fixed metadata fields
into a 56-byte stack buffer. One entry uses 3 SHA-256 update calls instead
of 8, with the same input byte stream and exact digest. No file metadata
calls or journal/cache format changed.

Apply `source.patch` to exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`. For the
specific #836 → #843 → #849 → #850 tree in the receipt, use the embedded
alternative instead. Exact apply and reverse verified. Four optimized
unmasked storage libraries built, 115 tests passed and one ignored each.

Native direct-function comparison uses preconstructed synthetic maps with
4096 paths, paired and alternated across eight runs per arm. The test source was
optimized; both arms used the same locked debug dependency pool. Stock medians
were 6057.3 → 5115.2 µs per digest, paired
median improvement 15.7%. This is not an app or
startup benchmark.
