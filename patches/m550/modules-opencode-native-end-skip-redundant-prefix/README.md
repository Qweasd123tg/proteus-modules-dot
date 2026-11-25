# OpenCode JS: skip redundant prefix checks on completed text

An authoritative end event can only extend the streamed text when its final value is longer. Skip the prefix check when it is not, while still storing the final content exactly, including shorter or same-length corrections. Text and reasoning use the same path. Longer end values, absent payloads, and established validation and stream ordering stay unchanged.

The exact local collector matched across 16 positive cases and four error controls in four arms. Independent equal-length final text and reasoning test blocks needed no prefix check or empty slice after the patch. The mixed four-block case went from four to one prefix check, with identical deltas, authoritative completion, output ordering and metadata.

The pinned producer was checked from release source. Local execution used synthetic events, not a live OpenCode provider. The reported comparison/slice call counts do not measure bytes scanned, runtime or RAM.
