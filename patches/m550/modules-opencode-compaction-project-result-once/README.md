# OpenCode compaction: project tool results into one array

When an assistant tool call is paired with a stored result, the OpenCode compaction adapter starts with the existing output text and appends each projected text or inline image to that same array. Previously it projected the parts to a separate array and then copied its entries into the array with the leading text.

The leading output block, part order, inline image bytes and supported-content checks are unchanged for canonical JSON results. The patch does not change compaction decisions or the model provider. The checks run the actual projection with inert SDK seams; they are not a full OpenCode run or a Proteus memory benchmark.
