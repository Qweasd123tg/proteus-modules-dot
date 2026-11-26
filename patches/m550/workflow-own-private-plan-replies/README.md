# Move terminal private plan output into model history

A terminal plan was cloned into the model-only history and the tagged
originals were dropped. Move the tagged messages into that history.
Private IDs, provenance, request scope, usage bookkeeping, and the
different treatment of persisted tool-round plans are unchanged.

Directly applicable to Modules 5377853779ae499b03ff152b97eb1c11eaa64ed2,
with exact forward/inverse tree checks. Two clean optimized libraries
built and two isolated, synthetic no-tool tests passed per arm. At the
private plan ingestion seam both original text buffers were kept after
the patch (48 KiB total); before, neither was kept. Output and private
scope assertions still pass. No application RAM or latency claim.
