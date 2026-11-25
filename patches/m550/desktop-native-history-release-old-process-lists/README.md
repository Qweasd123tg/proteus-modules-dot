# Native-history observer: release old per-process details

The observer needs the full process list from the final sample to validate the session snapshot. Once it has written and flushed a sample to JSONL, it can release that list before taking the next sample. It still keeps the scalar and grouped data from every sample for its report, and the raw JSONL still includes every process list, including partial results after errors.

The Core sampler, memory and timeout guards, and application are unchanged. This reduces retained lists in the benchmark observer, not measured Proteus memory.
