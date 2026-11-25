# OpenCode compaction: convert tool-result tail directly

When an ordinary native result array begins with text, keep that text as output and project the remaining blocks straight into the canonical content array. The conversion no longer allocates a separate tail slice. Attachment validation, block order, gaps in ordinary arrays, error envelopes and the fallback for other shapes remain unchanged.

The paired checks use the actual local compaction callback with an inert SDK conductor and synthetic host replies. They do not run the pinned OpenCode SDK, tools or a model, or measure application memory or time.

The patch header targets current packaged Modules. The scoped composition after #741 has the same two hunks four lines later; its exact before/after hashes are in the receipt. This is not a full M502 reconstruction.
