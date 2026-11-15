# Settings Reload × Save: accepted-profile revision boundary

Source-only candidate for the known [PR85 finding](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85), not an installed or production-qualified fix.

See [REPORT.md](REPORT.md), [exact source review](SOURCE-REVIEW.md), [architecture review](INDEPENDENT-REVIEW.md), and [patch](settings-profile-revision.patch).

One shared snapshot-acceptance boundary invalidates older reads without disabling Save or repurposing edit_revision. History/addons are outside scope; edit→undo conservatively discards the old read.

Eight proposed Rust tests are **NOT RUN**. No compilation, formatter, native UI, HTTP or runtime execution. Strict patch application and exact resulting bytes verified; composition with [PR134](https://github.com/Qweasd123tg/proteus-modules-dot/pull/134) and [PR135](https://github.com/Qweasd123tg/proteus-modules-dot/pull/135) is text mechanics only.

Source manifests record pinned public repository identities. Baseline source copies and raw private execution logs are intentionally not published. SOURCE-CHECKS.json contains normalized command basenames, not a standalone test runner. Production qualification gates are in REPORT.md.
