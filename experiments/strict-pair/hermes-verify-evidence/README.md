# Hermes-inspired completion gate — explicit receipt policies

Our isolated example copy adds mandatory `receipt_policy` selection:

* `strict_json_contracts`: v2 only, expected suite/config SHA256 and exact
  document/path/assertion-ID/pointer coverage; fail-closed exhaustion required.
* `advisory_v1`: explicitly requested original unpinned v1 semantics; no strict
  coverage guarantee and no automatic fallback from v2.

The host-owned hook/v6 lifecycle and retained-history freshness algorithm are
unchanged. This is not an upstream Hermes runtime/API compatibility claim.

See [paired README](../README.md), [validation status](../VALIDATION.md), and
[source pins](../SOURCES.md). The initial upstream-inspired tests now explicitly
select advisory_v1; new tests exercise strict producer/consumer binding.
