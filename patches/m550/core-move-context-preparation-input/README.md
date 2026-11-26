# Core: move the context preparation input instead of cloning it

The workflow host previously cloned the whole typed input before calling context preparation. It now keeps only the reason, message count and optional token estimate for telemetry, and moves the input into the same preparation call. Started/Completed/Failed events and the public report fields stay the same. Preparation itself still validates and processes the original request.

A fresh locked/offline Rust build passed 73 focused tests from the patched source, including context preparation, workflow replay and checkpoint regressions. One separate private diagnostic ran the reference Codex workflow with synthetic history, a fake model and an inert local hook; it checked callback telemetry for both success and failure. The diagnostic is not in this patch. This is not a test of the installed standalone Coding Workflow worker or a measurement of application memory or timing.

Apply only `source.patch` to the exact Core owner and two preimages in `receipt.json`. No alternate. #806 and #809 are independent; their combined order was checked only at the source level.
