# Desktop: build Copy/Cut clipboard text directly from selected ranges

For a single selection the base input converts the Rope slice directly into its final owned String. For multiple selections it preserves document order, emits one newline between nonempty ranges and appends only the selected Rope chunks. No intermediate owned String per range and no full-document flattening. Masked and empty selections still cannot copy or cut.

The scoped native check covered 20 cases, Copy and Cut, 160 A/B/B/A allocation ledgers. For a 2 MiB single selection, peak requested heap was 4,194,328 → 2,097,408 B; retained clipboard text was 2,097,152 B in both. Copying three ranges totaling 2 MiB had the same near-halving. Byte-for-byte output and Cut callback order matched. This is not a GPUI, system clipboard, timing or process-memory benchmark.

For the measured full leaf on the verified owner revision, apply #680 first. The full five-leaf prerequisite followed by this change was applied and reversed on the exact stored owner files. See receipt.json.
