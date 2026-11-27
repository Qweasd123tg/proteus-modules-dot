# Defer the current user copy until pre-turn repair

After locating the original current user, prepare only the preceding
history as before. Take the prepared history out of the request on all
paths; append a current-user clone only when the report changed and
repair will consume it. An unchanged report is still recorded. The
sampling request still takes the same model messages and controls.

Exact Modules basis: f4bd470def2255f3459b7a42b50e96d0faa0bbf1.
For synthetic current text of 160 KiB, the measured temporary copy
allocated 164,000 requested bytes in 2 calls before the patch and
none after on unchanged or rejected preparation. Changed preparation
retained the same copy. Invalid-anchor control stayed at zero.
Seven focused native checks and two unmasked optimized standalone
libraries; no provider, whole-app latency or peak-memory measurement.
