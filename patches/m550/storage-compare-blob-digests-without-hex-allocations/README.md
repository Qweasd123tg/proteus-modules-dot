# Compare verified blob digests without an intermediate hex String

For a raw expected payload, each newly verified packed chunk, and the final
packed payload, match the SHA-256 result against the same exact lowercase
ASCII text without materializing another String. Hash inputs and count,
limits, recorded encodings and verification order are unchanged.

Apply to exact Modules `5377853779ae499b03ff152b97eb1c11eaa64ed2`. Full indexed apply and reverse
verified; two optimized unmasked storage libraries built. 116
tests passed and one ignored per arm.

Synthetic valid raw: one fewer allocation request (64 bytes). Packed
A/B/A: three fewer requests (192 bytes), from two unique chunk checks and
the final digest. The raw read without an expected digest is unchanged.
Byte ownership and exact success/error conditions were verified. These
are allocator requests, not app memory or startup time.
