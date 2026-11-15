# Root tool projection: source-only proposal

Delivery-only package for the known PR85 reconnect finding. Upstream Core/Modules source, dependency pins and binaries are unchanged.

See [report](REPORT.md), [exact independent source review](ROOT-TOOL-INDEPENDENT-REVIEW.md), and [patch](root-tool-result-projection.patch). Reports describe the investigation before publication; this delivery package does not apply the patch upstream.

The proposed fix retains full root tool text while preserving bounded foreground/background nested child previews. Production code grows by 3 lines. This costs additional retained memory and snapshot copies; structured fallback and aggregate budget remain unresolved. There is no universal 200000-byte bound.

Publisher reverified all 20 Git blob identities, strict whitespace patch application and six exact after-file hashes. Two proposed Rust tests, compiler, formatter, application/HTTP/GUI and cold storage checks were NOT RUN. No runtime or Python behavioral model was run. Independent source review is not runtime acceptance.
