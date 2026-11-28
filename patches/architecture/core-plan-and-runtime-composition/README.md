# Separate the Core assembly plan from runtime construction

Standalone patch for Core `024fb944a91382026bb2aa5c7b8da65c284d0305`. Verify `sha256sum -c SHA256SUMS` and apply `source.patch` to a detached checkout. The same patch also applies after the verified Core stack with #955.

Plan resolution no longer imports the runtime registry. The existing PreparedAssembly owns runtime composition in a sibling module; the public Core re-export and the Registry convenience constructors keep their signatures and behavior. The registry still builds from the validated plan, and a running turn still sees its originally admitted snapshot.

Selection, validation order, error paths, injected storage priority, shared Arc plan and registry, public JSON and protocol are unchanged. Plan inspection can read supplied configuration metadata but does not start unrelated workers. See receipt.json for verification.
