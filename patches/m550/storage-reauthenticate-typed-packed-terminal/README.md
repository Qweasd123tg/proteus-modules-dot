# Reuse the freshly validated typed terminal after authenticating its bytes again

A fresh strict fold can keep the one record and a small exact journal
line in the same ReadRecords call. The next read still traverses the
same pinned cursor and authenticates the manifest, every unique chunk
and complete SHA-256. On a byte-identical header it skips rebuilding
the packed body and parsing that payload JSON again. Changed lines,
non-singletons and other backends retain the existing path.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. The 50,000-message packed singleton
returned the byte-equivalent typed page in **357.7 → 274.9 ms** median
across eight rotated pairs on an isolated Linux backend, with worker
peak RSS **146,928 → 147,188 KiB**. Inline control was about 0.4 ms
on both. The native full suite plus three focused controls passed
119 tests, one ignored per arm. Both separately combined #887/#899
variants also passed the unmodified 116-test suite, one ignored.

Use source.patch on the exact base, or the exact forward/inverse
composition variants in the receipt. This is measured storage
page time, not app startup, PSS or a full M650-stack claim.
