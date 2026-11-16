# Resolve inline role aliases in the effective child scope

Source-only candidate against Core `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`. Native tests and Rust compilation have NOT run; publication is not an upstream change or runtime acceptance.

## Contract and source-level failure

The [configuration guide](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/docs/guides/configuration.md) presents `role.model` and `role.config.model` as alternative locations for the explicit choice, and permits inline roles to define local named presets.

In the current normalizer, a string on the role is looked up and converted against the parent catalogue *before* the inline child's local catalogue is merged. Therefore a child-only alias fails the parent lookup when written on the role, whereas the equivalent choice inside its config reaches the local catalogue. A parent-existing name shadowed by the child already follows the child's final choice, making the early parent lookup both inconsistent and redundant for inline roles.

This is established by direct source tracing and independently reviewed against the guide, not by a claimed Rust execution.

## Minimal repair

Keep the role choice as an unresolved name until the normalizer knows its scope:
- inline child: inject the name into the child source and let existing child normalization resolve it after catalogue inheritance/local overrides;
- external/no-inline child: retain the existing parent-catalogue lookup and conversion.

No new resolver, fallback, catalogue copy or compatibility mode is introduced. Explicit-object choices, dual-selection rejection, transport binding logic and default inheritance remain unchanged. This is different from #167's file-include Save spelling repair.

Three proposed tests extend the existing models test module: role/config placement equality for a child-only alias; unknown external choice still rejected; child shadowing preserves the parent's own model. They are source proposals only, not passing native results.

## Verified and not verified

- Both source files and the guide match exact upstream Git blob identities; Core main remained at the pinned ref.
- Independent source review accepted the scoped resolution change.
- Strict whitespace apply, exact candidate bytes, reverse and exact baseline bytes verified.
- Mechanical composition with both published #167 patches also applies and reverses to all original bytes. This is text compatibility, not combined behavioral acceptance.
- Rust/Cargo, rustfmt, native tests, real config loading, agent runtime, providers, hosted CI and benchmarks: NOT RUN. No Python emulation is offered as a substitute.

Adoption still needs the repository's actual Rust formatting and focused config/model tests in an equipped environment. No performance gain or global model-selection correctness is claimed.
