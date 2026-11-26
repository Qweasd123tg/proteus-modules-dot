# Modules: move compact reasoning strings into storage replies

The storage reply adapter now moves already-owned Reasoning text, signatures and summary strings into the existing typed reply slots when they are at least 4 KiB and have no spare capacity. Smaller strings or strings with spare capacity still follow the existing serializer path. Absent signatures remain distinct from empty signatures. Envelope, field order, existing Text/Opaque handling, storage contents and transport limits are unchanged.

Three focused tests passed in an isolated Rust 1.95 build. The typed adapter test confirms exact serialized bytes and ownership transfer only for eligible strings. Separate stock and candidate workers negotiated actual display projection on the same synthetic JSONL and SQLite fixtures: four operations per backend produced matching ordered results after normalizing only generated handles and fixture locators. Both rejected reads after release.

No change to Core or the SDK dependency pin. No production eligibility rate, Desktop timing, application memory or end-to-end speedup was measured.

Use `source.patch` only on the exact Modules owner and path preimages in `receipt.json`. #618 and #664 are already integrated. There is no alternate.
