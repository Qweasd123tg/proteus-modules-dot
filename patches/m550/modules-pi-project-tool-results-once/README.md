# Pi tools: project result text and images in one pass

Build the display text and canonical image blocks from the result without creating disposable canonical copies of the text blocks. Preserve block order, the first unsupported-block diagnostic, error handling, and metadata.

This change runs after a supported Pi tool returns, not during tool selection or execution. The receipt records isolated normalization checks and structural counts, not an actual tool run or application timing or memory.
