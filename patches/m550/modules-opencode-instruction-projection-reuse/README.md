# OpenCode: reuse the filtered array when projecting instructions

Keep the original filter and event processing order. When there are generated instructions to insert, collect their positions and expand the private, already-filtered array from the end in disjoint ranges. Keep the existing output when no instructions are inserted. Deduplication, validation, identity generation, marker handling and message order are unchanged.

The exact local BeforeModel hook passed 24 paired controls with inert upstream dependencies. On 50,000 synthetic messages and six generated insertions, the old code kept a filtered source and a separate 50,006-entry result; the changed code reused the filtered array and tracked six temporary placement records. Final output was byte-identical. The result establishes array-object reuse, not backing-store allocation bytes, time, or application RAM.

The patch applies to current pinned Modules, which already include #726. The scoped preimage is byte-identical.
