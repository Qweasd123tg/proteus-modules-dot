# Adapted package runtime supplement

This supplement supersedes only the earlier *not yet executed* packaging status in the frozen README and evidence metadata. Those files preserve their original source-review state; no executable or configuration payload was changed for this publication.

On 2026-10-26 the exact adapted public layout was separately retested and independently reviewed. The package's CODE.sha256 digest is a5a0fd3a9f360120c00dc6508e227cfabe21070d5c25ddd88b4d806f86e7630f.

- 45 Python controls passed: 18 configuration, 18 oracle, and 9 controller mocks. Three isolated Python children exited and were reaped cleanly. These are helper checks, not Node or Core execution.
- A separate run passed 38 pure JavaScript controls and 13 SDK hook calls plus initialization. The raw exchanges independently confirmed four precise unsafe-integer refusals without error.data, two unchanged Continue results and seven replacements, including safe-42 recovery.
- The two direct Node children exited successfully and were reaped. Original public payloads and selected runtime inputs matched their before/after hashes. No Core turn, provider call or real tool was executed.

The selected Node runtime was v24.19.0 with SHA256 bc17c508ffeed0ec622934f9b7fa72f8e78da65350e63c3eceb56fa688aa5e12; the Python runtime had SHA256 fa67443527ed9647f760d807e2a38f26340757123e643c4639cf273ed15d5ea7. These are observed platform identities, not vendor authentication or cross-platform support claims. SDK inputs remain explicitly pinned in the package; consumers must provision trusted inputs themselves.

The guard only inspects outbound replacements at inspection time. It cannot recover already-rounded inputs, prevent subsequent mutation, enforce host authorization or guarantee underlying-tool denial after an error. A computed safe zero derived from rounded inputs and a later unguarded handler were explicit accepted limitations, not missing negative cases. There is no parser-losslessness, OS-isolation, whole-descendant-cleanup or performance claim.

This is summarized local evidence, not remote CI acceptance. No CI workflow or SDK download is added by this delivery. Raw execution receipts and local workspace paths are intentionally not published.
