# Let the session catalog own its prefix cache

Standalone Modules patch on `7274147162cb226f05df13a52b4a271fa5619313`. Verify `sha256sum -c SHA256SUMS` and `git apply --check source.patch` from a detached Modules checkout with the absolute path to the patch.

A read view depended on the catalog for the source and blob stamps, but the catalog depended on that view for the validated prefix cache. Move the unchanged cache type, validation and insertion to the catalog, which already owns every write to it. Views and display read it from the catalog. This removes eight direct catalog-to-views references and adds no abstraction.

The public storage module contract, backend selection, validation, on-disk v1 encoding and eviction order are unchanged. Core, Desktop and Extensions need no corresponding code changes. See receipt.json for exact tree and native test evidence.
