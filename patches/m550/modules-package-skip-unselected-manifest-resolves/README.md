# Modules packaging: skip canonicalizing unrelated Cargo manifests

A Cargo artifact whose typed target name is absent from the selected binary names cannot be a selected executable. Keep it in the complete target audit, but avoid canonicalizing its manifest. Matching names still need the exact canonical manifest, binary kind, non-test profile, output count, existing executable and existing SHA-256 checks. A same-name artifact from a different manifest is not accepted. Package staging/publication rules are unchanged.

The evidence exercises the actual Python packaging path with controlled Cargo output and real temporary fixture paths. In the 420-record synthetic stream the manifest resolution count changed from 417 to 5 and all 414 target audit names stayed intact. This counts resolutions, not I/O syscalls or build time. No real Cargo or Proteus runtime benchmark is claimed. An unrelated path in an artificial record can no longer trigger an incidental path-resolution error; actual typed Cargo records describe manifests of compilation units.

Apply `source.patch` to the pinned Modules revision, which already includes #721.
