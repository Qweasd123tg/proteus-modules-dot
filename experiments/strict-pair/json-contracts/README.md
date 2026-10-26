# JSON contracts producer — strict paired v2

This crate now emits only the shared local v2 receipt. Use it with the strict
consumer in the parent workspace; the standalone v1 milestone is separate.

See [paired README](../README.md) for the full trust/bounds contract and operator
workflow. `JsonContracts::expected_policy()` and the stdin-only `strict_json_policy`
example derive exact consumer expectations from validated producer config.

Rules remain `exists`, `type`, `equals` (exact integer-only numeric domain), and
`non_empty`; read_file full-read metadata is validated before JSON assertions.
No model arguments can change paths, rules, results or coverage. No direct
filesystem/shell/model fallback exists in production.

The earlier v1 logs were moved out of this crate and do not establish v2 success.
Current validation status: [workspace evidence](../VALIDATION.md).
