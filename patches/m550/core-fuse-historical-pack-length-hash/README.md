# Core: count and hash a historical display pack in one pass

The historical cache reader checked the physical pack size by serializing its value, then serialized it again to compute its canonical SHA-256. The new reader checks the existing one-field shape first and counts bytes while computing the same digest. The inclusive 256 KiB cap, leaf count, exact hash, compression, bounds and fallback are unchanged.

This removes one local serialization of an already decoded historical pack. It does not change the durable journal, cache format or public wire, and does not skip cache reads, input decoding or leaf integrity checks.

On Rust 1.95 in a separate target directory, one Contracts test and 35 Core tests passed. The cap and canonical SHA are checked at the boundary. No Desktop timing, application memory or end-to-end speedup was measured.

Use `source.patch` only on the exact Core owner and three path preimages in `receipt.json`. No alternate. #600, #604 and #626 are already present.
