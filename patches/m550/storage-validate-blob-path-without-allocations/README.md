# Validate a JSONL blob reference without allocations

Use the same native path components iterator and compare the borrowed
filename stem directly with the lowercased ASCII hash bytes. The path,
error precedence, allowed hash text, strictly lowercase filename, and final
content identity check are unchanged. Do not infer that a mixed-case wire
hash now passes content validation.

Apply to exact Modules `6b290ebff828427ab66ef9c4ff3b24cef3627603`; full-index apply and reverse
verified. Two optimized unmasked storage libraries built; 115 tests passed
and one ignored in each arm. The focused codec regression compares both
validators over a lexical path matrix and exercises inline, raw external,
and packed external records. In the isolated valid reference check,
4 allocator requests totalling 480 bytes became zero.
No whole-decode or application-memory claim.
