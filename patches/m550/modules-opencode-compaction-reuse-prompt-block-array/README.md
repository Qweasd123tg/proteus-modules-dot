# OpenCode compaction: reuse the projected prompt array

Keep the existing complete payload projection and validation, then fill the private projected array with canonical part wrappers instead of allocating a second array. The existing first-part wrapper and metadata are kept. Empty lists, ordinary sparse indices and generated identifier order stay the same.

The exact local compaction callback was exercised before and after with an inert upstream driver, synthetic host response and deterministic test-only UUIDs. The change does not run tools or a model, and the verification is not a pinned SDK or application memory/timing benchmark.

The patch targets current packaged Modules. Its equivalent scoped hunk after #741 and #745 and the before/after hashes are recorded in the receipt. This is not a full M503 reconstruction.
