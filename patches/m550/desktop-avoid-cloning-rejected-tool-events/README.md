# Desktop: stop cloning tool arguments for an already-full child

One production patch against exact Desktop M404
(`0eb5584908b5908298787fa8e07a41f8aa02430b`). In the typed Proteus
runtime-event fold, construct the visible tool record only after
admission. A running child's 64-tool display cap already discarded
the next tool; it no longer deep-clones the discarded arguments
first. This is not a runtime invocation limit, a wire-size limit, or a
change in what runs on the server.

The child's capped event still returns the same `Change::Updated`,
does not publish a standalone tool, and does not detach shared
progress. A 64th accepted request still retains the complete typed
arguments; root, unknown, completed-child, and newest-running-duplicate
routes keep their existing behavior. No changes to stdout, SSE
framing, renderer, Node, authorization, or application limits.

## Scoped native evidence

The harness serializes and decodes the real `AppServerEvent::Runtime`
with the complete authenticated M404 Contracts crate (113 unchanged
files); it then invokes exact Desktop `Transcript::apply_runtime`
and `stamp` as the UI's runtime pump does. Both Rust JSON map modes
compare seven route controls and all transcript tests. The only
test boundary is the GUI pump calling the same native reducers: no
whole app, graphics, device or SSE transport stand is claimed.

One already-decoded, 2,279,835-byte wire-equivalent payload is
replayed four times at the existing display cap. Measured within
the reducer and timestamp call, not during serialization or decode:

| Mode | Gross allocation bytes, stock → candidate | Requests | Added peak in measured scope |
| --- | ---: | ---: | ---: |
| Default map | 9,289,640 → 144 | 1,088 → 4 | 2,322,410 → 36 B |
| Insertion-order map | 9,229,608 → 144 | 1,352 → 4 | 2,307,402 → 36 B | |

Retained allocator delta is zero on the capped arm; existing parsed
arguments are outside and untouched. The same-sized admitted 64th
request and the other control routes show identical alloc counts and
canonical row contents per mode. Neither this peak delta nor
cumulative requested bytes is process RSS/PSS, saved-history latency,
or a whole-app improvement.

`composition.json` authenticates stock and candidate and shows that
the patch needs #642 (archive child COW) first. The exact #645
saved-geometry selector commutes in both orders; #646 is Core-only
and doesn't touch Contracts. The companion production test is not a
separate patch. Reproduce with Rust 1.95.0 and the verified Cargo
vendor closure:

```sh
sha256sum -c SHA256SUMS
python3 verify.py --vendor /path/to/vendor
```
