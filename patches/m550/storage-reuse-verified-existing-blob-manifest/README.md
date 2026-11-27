# Reuse the verified manifest on existing packed JSONL writes

An existing packed blob already had to be fully decoded to verify
that its data equals the intended write. Return that same manifest's
descriptors for the touched paths rather than parsing it a second time.
Chunk and whole-payload checks, equality, path order and repetitions,
and raw/new object behavior remain unchanged.

The exact Modules basis is `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`.
Both arms built optimized standalone libraries and passed 117 tests
(one ignored per arm). The typed JSONL writer witness saw **2 → 1**
manifest parses, with the same journal line and all 17 chunk
references in the same order, including repetitions. The test also
covers fresh/raw paths, collisions, malformed manifests and missing
or corrupted chunks. Full application latency and RAM were not
measured. Source overlap with drafts #854, #855 and #875 is recorded
in the receipt: rebind source patch context rather than blindly stacking.
