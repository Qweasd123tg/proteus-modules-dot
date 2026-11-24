# Modules: borrow ordinary workspace path components

The workspace decoder now borrows an ordinary, unescaped component instead of allocating a decoded buffer and a second buffer to check its spelling. The fast path uses the encoder’s own character rule, so the spelling is unchanged. Escaped and other inputs still use the original decoder and diagnostics. The existing component check, filesystem canonicalization and final comparison of the encoded workspace name are unchanged.

Four tests passed on Linux, including the unchanged original workspace encoding test in both variants, plus 68 observations across 17 fixtures in stock/candidate/candidate/stock order. Results and diagnostics matched, and the escaped and error controls had identical allocator traffic. For the nine-byte `workspace` component, peak requested bytes went from 25 to zero and allocation requests from three to zero. A synthetic 40 KiB component, tested only in the component decoder, went from a peak of 106,496 requested bytes and 15 requests to zero. These results measure allocator requests for component decoding, not whole-path or application memory, RSS, or latency.

The exact indexed patch applies and reverses on Modules main `e8e77e306092344c00833f3456acba950c851fe3` and on the packaged Modules pin `a271aaefcbcdd25f9b68918406f34490c6169bd7`. No earlier patch is required.
