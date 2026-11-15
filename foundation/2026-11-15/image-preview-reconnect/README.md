# Image-preview reconnect candidate

An isolated follow-up to the known PR85 sticky image-preview failure. See `REPORT.md` for the exact scope, evidence and limitations and `DESIGN-DECISION.md` for the selected scheduled-before-reconnect policy.

Apply `image-preview-reconnect.patch` only to Desktop `7eaf70c67dabba8595d98029c875ffc3f59209ad` or review/rebase deliberately. It touches four files. No other candidate is a prerequisite.

**Not compiled, not run, not production-ready.** Rust/Cargo/rustfmt are unavailable. Five added Rust tests are proposals, not passing results. Text verification and independent source review do not substitute for actual queue, HTTP/decode and native redraw validation.

Publication files are listed in `PUBLIC-FILES.json`; raw snapshots, the isolated candidate and text reconstruction are not intended for delivery. No live data or real attachment was used.
