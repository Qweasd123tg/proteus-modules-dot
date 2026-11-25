# History benchmark verifier: reuse the checksum for the default full fixture

When no active-tail option is supplied, the display messages and the active model messages are the same validated list. Reuse the count and checksum already computed for that list rather than serializing and hashing it again. Explicit compacted tails and their independent checks stay unchanged.

Sixteen exact Core Python CLI pairs matched using synthetic local journals and blobs. Seven successful reports were byte-identical, and nine rejected inputs kept their existing diagnostics. The stock preservation tests passed on both versions. In the default 4,096-row fixture, the observed compact JSON encodings for the digest fell from 8,192 to 4,096. Explicit tail and auxiliary validation stayed intact.

This is preparation of benchmark fixtures before the application run. No native seeder, application or runtime benchmark was executed.
