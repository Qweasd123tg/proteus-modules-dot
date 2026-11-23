# Desktop: borrow cached thumbnail lookup keys

## Change

Base: [Proteus-desktop f8cc40177ad3ab3d8ec36447a899332778f03268](https://github.com/Proteus-harness/Proteus-desktop/tree/f8cc40177ad3ab3d8ec36447a899332778f03268). One hunk in `src/ui/chat/images.rs`. Existing per-view slots already own their thumbnail keys. Compare the requested connection, directory as `Path`, ID as `str`, and edge against the slot key, in the original derived equality order. On a match, borrow that same key for the existing shared-cache lookup and pass the same owner. Remove an incompatible slot before processing demand, as before.

This avoids constructing an owned directory and ID at render-time for each image occurrence. If there is no slot, don't touch the shared cache by key: return the same independently owned missing ID and let the scheduled fetch construct the real request key. The outgoing `Vec<String>`, thumbnail request key, completion ticket, weak lease, rearm credit, pruning and LRU order are unchanged. No changes to path handling or security boundaries: `Path` equality handles component normalization and non-UTF-8 names exactly as the prior `PathBuf` equality. Neither canonicalizes paths or accesses the filesystem.

## Proof and scope

`proof.py` verifies the three pinned Git blob IDs, checks patch application and formatting, compiles both variants at optimization levels 0 and 3 with Rust 1.95.0, validates allocation witnesses, reverses the patch, and compares the restored production file byte for byte. `lift.py` copies the exact production Key, Slot, SentImages and shared Cache implementation into an inert harness. The exercise calls the real `SentImages::missing` and real cache logic. It models only external types/boundaries: GPUI App/Bitmap/scene-lease predicate, decoded Preview and ImageRef/Entry shapes; no renderer, queue worker, network, decoder, display, or full Desktop binary. Five upstream ticket/retry cases are lifted from the pinned tests with just test attributes removed. Additional cases cover equivalent-but-raw-distinct normalized paths, preserved leading-dot and parent-segment distinctions, matching and distinct non-UTF-8 Unix paths, mismatches of all four key fields (including an inconsistent stored ID), stale owner release/GC, LRU promotion and new-owner adoption, cache hit without a corresponding slot, duplicate demands, ready/failed/waiting/loading transitions, and the two scene-lease outcomes. Native GPUI/compositor integration was not run.

The allocator is measured only on the fixture thread during the call. It counts allocation/reallocation requests and requested bytes, not allocator usable size or live/peak memory. All inputs and prepopulated cache fixtures are prepared before observation. Both optimization levels produced:
- 64 repeated ready hits with a 52-byte directory and 35-byte ID: 128 → 0 requests; 5,568 → 0 bytes.
- One no-slot demand: 4 → 2 requests; 218 → 131 bytes. The returned ID allocation and output Vec remain.

This is an image-row hot-path reduction. It does not apply to text-only 50k history and does not establish an app latency or PSS change.

## Reproduce

With the pinned Desktop source and Rust toolchain available:

```sh
sha256sum -c SHA256SUMS
python3 proof.py /absolute/path/to/desktop/source /absolute/path/to/rustc /absolute/path/to/rustfmt
```

No crates are downloaded or built by the proof. The output is included as `evidence.log`. `SOURCE-PROVENANCE.json` identifies the exact baseline fixtures and the one postimage.
