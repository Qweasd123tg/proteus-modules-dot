# Desktop: share saved draft text with its composer row frames

Copy listeners share the existing immutable String instead of each retaining a
full draft copy while the unsent strip is displayed. Restore retains its original
text/attachment behavior, and Copy still creates the owned String required by the
clipboard only on a click. Older frames preserve the bytes they showed.

A bounded native fixture covered 12 inputs and 192 allocation ledgers. For a
2 MiB draft and three simultaneously held row frames, scoped requested peak and
retained allocations were 6,292,110→654 B, excluding the already-owned draft.
One 40 B control allocation is added per saved draft, including small or empty
ones, and old frames can keep the source's spare capacity until they are dropped.
This measures frame capture and the String input to Clipboard, not actual GPUI
render, UI latency, OS clipboard, or process memory.

Exact M439 Desktop patch; on a source base lacking #680, apply that prerequisite
first to match the retained draft preimage. #681 is independent. See receipt for
source pins, controls, measured phases and hashes.
