# Skip a proven throwaway stage for a JSONL singleton

After strict typed replay has accepted the first physical record, the
already-decoded row is known to end at the same pinned complete extent.
If it is the existing singleton history case and its emitted Text
fields alone reach the staging decline threshold, do not serialize
it to the private display file. This leaves the ordinary EOF,
fingerprint/metadata retry, catalog and canonical fallback in place.

Exact Modules `f4bd470def2255f3459b7a42b50e96d0faa0bbf1`. In a synthetic packed 50,000-message
single record the full display stage went from **33,100,402 to 0**
logical serialized bytes, including LF. The canonical typed record and
the journal bytes were unchanged, with the same strict display decodes
and first fallback page. A large first record with a later HookInvoked
still publishes a display projection. Small and escaping-bound cases
take the previous path. Both arms passed 117 tests (one ignored) and
built optimized standalone Storage libraries.

No full-app speed/RAM, device-write or extra history-scan savings claim.
Use the same-file #861 rebind only on its exact pre-tree. #885 is
file-disjoint; the earlier architecture's #856 is not stackable.
