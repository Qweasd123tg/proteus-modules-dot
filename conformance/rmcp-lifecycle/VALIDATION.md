# Validation — actual SDK/client fixture gate passed

On 2026-10-25, [CI run 40246861740](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40246861740)
passed at exact tested commit `1d60afe8ef9a903a1bf5e0f1c726375e1501fa9e`,
tree `7c9d67b64f34156218c3d0b1fb1831a0ea692792`.

- **33 Rust cases passed:** 12 typed decode, 2 responder controls, 19 actual SDK
  client/authored stdio lifecycle cases. Zero failed, ignored, measured or filtered.
- Eight separate Python evidence-verifier controls passed. These use authored log
  strings and are not counted as Rust or MCP runtime cases.
- Locked dependency fetch, offline metadata, Rust compilation, `cargo fmt --check`,
  and the exact named-case/evidence gate passed on Ubuntu 24.04 x86_64, Rust 1.95.0.
- All 17 source/gate hashes matched the reviewed `CODE.sha256` and were identical
  before and after execution. The initial source-only commit was correctly marked
  pending; this update records actual results without changing those source bytes.

[Artifact 12619350215](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40246861740/artifacts/12619350215)
was downloaded and its ZIP SHA256 verified:
`f96932d00103374ee9df47cb4a36cbd75fef157c992c29e83182bbb0e2545bfd`.
All captured phase exits were 0; the independent local recheck of the downloaded
artifact accepted the same 33 exact names and unchanged source manifests.

Retained portable receipt files: `validation/receipt.json`, `tests.stdout`,
`result.json`, `source-hashes.json` and `source-hashes-after.json`. The workflow
artifact additionally contains commands, toolchain details, full build/metadata
logs and exit files. It expires after 14 days; the compact repository receipt
retains case results and source identities without copying runner-local paths.

## Supported findings and limits

The raw/typed boundary checks now have runtime evidence: supported Tool metadata
survives, unknown fields and the legacy experimental task hint are lost at typed
decode, and malformed known fields are distinguished from unknown-field loss.
Default `.serve()` still initializes even with the modern version string; explicit
Discover/Auto use the tested lifecycle. Matching/omitted versus mismatched error
IDs, domain failure, MRTR single-round behavior and timeout/caller-abort cases
have separate controls. The unanswered-probe test establishes fallback within
caller budget, **not an exact 10-second timing measurement**.

This is not a real Core invocation, complete protocol compatibility result,
third-party server test, full agent turn, external-model check, OS sandbox proof,
or Core admission/cancellation/settlement proof. Source-based Core observations and
proposed host changes remain distinct. No dependency security audit is claimed.
