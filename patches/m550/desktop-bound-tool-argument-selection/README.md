# Desktop: bound tool argument row selection to six entries

Expanded tool details show at most six additional arguments. The previous helper gathered and sorted every eligible pair before formatting those six. This patch keeps the six smallest keys in a fixed stack, preserving the displayed order, filters and text formatting even in insertion-ordered JSON.

The native scoped check used the actual helper and pinned serde_json. All 20 cases and 80 allocation ledgers passed. With 128 argument fields, requested peak during row selection and formatting was 2,424 → 376 bytes. A synthetic 65,536-field map went from 1,966,064 → 376 bytes. The six displayed rows and retained 376 bytes were unchanged. The input map itself, GPUI rendering, runtime and process memory were not measured.

The exact source applies and reverses on the verified owner revision without a prerequisite.
