# Analysis: pre-size styled text and release loose formatting first

Construct the exact three- or four-field ordered object instead of growing a
three-field label when adding size. Drop the original loose String before
allocating the map. Text, tone, size, order and selection are unchanged.

The isolated guarded gate compared 108 exact serialized results across 18
fixtures and measured 72 allocation ledgers plus three stage traces. The
400-step list retained 125,112 fewer requested bytes, including the heading.
Its requested peak fell by the same 125,112 bytes, and total requested
allocations fell by 279,491 bytes. The loose-string peak fell from 954 to
578 bytes: the trace saw 545 original bytes drop to 33 before map allocation.
The tight large fixture also met the original peak threshold. Earlier held
patches and their failed receipts are unchanged. No application RSS, UI,
HTTP or latency measurements.

The changed leaf applies and reverses exactly on Extensions main and the
actual Desktop extension pin with no prerequisite. The tested supporting
text formatter includes #652. #673 reconciles the whole supporting SDK file,
but its five lifted helpers already match owner source; neither is a
prerequisite for applying this patch.
