# Count encoded storage metadata without allocating an output buffer

The Core Contracts guards write compact JSON into a byte budget instead of a
temporary Vec in metadata compare-and-exchange requests and metadata response
validation. The same compact serializer traverses the same Value, with the same
inclusive 1 MiB limit. The writer continues reporting successful writes after
overflow so the pre-existing serializer and validation error precedence stays
unchanged. No journal, wire schema, hash, or cache behavior changes.

Apply `source.patch` on exact Proteus-core commit
`b6d1bfee98488ab233048f36c87fb990f4ccba09`. Exact draft #799 is the only
selector touching either target. If #799 has already been applied to the
same base (tree `a9cb97c04bf35779ba243fe047f6e7909fc2366a`), extract and use the separately
verified alternate. Do not apply both.

```sh
jq -r '.selection.after_799.patch_base64' receipt.json | base64 -d > source-after-799.patch
```

Optimized direct rustc runs with pinned dependencies passed 160 Contracts unit
tests on stock and standalone, 161 with #799 alone and with both patches,
with zero failures and 0 ignored. Each arm passed 41 focused public
validation and wire round-trip checks. The
focused cases preserve inclusive byte boundaries with compact ASCII, escaped
controls, multibyte Unicode and nested values, null/deletion, ACK, missing revision and key
precedence. No full Core app build or cross-process storage run was claimed.

For a preconstructed synthetic 1,578-byte compact object, each of the three
touched validation calls went from 3 allocation/reallocation requests totalling
4,856 requested bytes to none. The 1 MiB accepted boundary was also checked.
These are isolated allocator counters, not peak or retained memory or latency.
Modules still uses its own pinned SDK version; no worker saving is claimed.
