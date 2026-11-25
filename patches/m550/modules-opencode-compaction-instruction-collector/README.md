# OpenCode compaction: collect checkpoint instructions in one pass

When the optional OpenCode compaction hook accepts a summary, collect its checkpoint instructions directly into one result array instead of building nested arrays for each history row and part. Keep message metadata ahead of its tool-result metadata, preserve the one-level flattening rules and existing diagnostics, and leave the model call, checkpoint, and skipped path unchanged.

Four local arms on the live and scoped sources matched across 16 controls. In each accepted 8,192-row fixture, the probe saw 8,192 intermediate part-collection arrays and 8,192 per-message result arrays before, and none of these temporary arrays after. The final collect-and-carry result is unchanged; the sparse run retained all 52 entries in order. The skipped run did not use this collector in either variant.

This is the optional compaction hook, not Desktop opening an existing history. Local checks used inert upstream boundaries and synthetic inputs. Counts are observed logical temporary arrays, not allocation bytes, process memory, runtime latency or end-to-end startup measurements.
