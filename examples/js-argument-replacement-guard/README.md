# Opt-in JavaScript argument-replacement guard

A small zero-external-dependency helper for cooperating Proteus JavaScript `before_tool` handlers. It refuses unsafe integer-valued Numbers **present in an outbound argument replacement at inspection time**. It is not a lossless parser, global middleware or authorization gate.

**Packaging status:** this public-layout candidate has not been executed. The helper, pure test program and SDK fixture are byte-identical to historically executed inputs; the optional probe's paths/configuration and public metadata were adapted and require retesting. See EVIDENCE_SUMMARY.json and PACKAGE_MAP.json. No SDK is bundled or downloaded.

## Pure use — no SDK needed to import the helper

```js
import { guardArgumentReplacement } from "./guard.mjs";

// At the end of a cooperating handler, after constructing nextArgs:
return guardArgumentReplacement({ action: "tool_arguments", args: nextArgs });
```

Return undefined or an ordinary Continue response when no replacement is needed; those pass through unchanged. Each replacement-producing handler must opt in. Existing SDK event/field validation, composition, schema checks and host policy/approvals are not replaced. The helper has no imports; no package installation step is needed.

To run the authored pure controls with a trusted local Node runtime:

```sh
node test-guard.mjs
```

Expected: one JSON record with status passed and exactly38 ordered control names from CONTROL_INVENTORY.json. This command is shown for the consumer; it was not run against this assembled public layout. The historical runtime was a pinned Node binary previously identified as v24.19.0, not every JavaScript engine/version.

## Conservative policy and limits

- Finite safe integer Numbers are accepted; exact ±2^53 are **refused despite being representable**. Nonfinite Numbers and integer-valued Numbers outside the safe range are refused. Finite fractional values have no decimal/lexical-precision guarantee.
- No stringification, number coercion, schema mutation or recovery of original JSON tokens. Agree on string-valued identifiers before parsing if that is the application's contract.
- Iterative walk limits: inclusive depth32 (root0),4,096 value nodes,65,536 UTF-16 key/string code units. Numeric array index names do not consume text budget. These are not UTF-8/wire, RSS, parsing-allocation or hard wall-time limits; own-key enumeration can allocate before refusal.
- Ordinary same-realm JSON-data trees only: dense arrays and Object.prototype/null-prototype objects with own enumerable string data properties. Accessors, special prototypes, non-JSON values, holes/extra array properties and repeated references are refused. Acyclic sharing is deliberately refused too. Proxies or modified intrinsic functions/prototypes are unsupported, not sandboxed.
- Accepted objects retain identity and remain mutable. The helper does not freeze/clone or control external aliases. Do not mutate the candidate after checking.

Two explicit non-guarantees were observed in the historical SDK fixture: a safe0 computed from already rounded input is accepted, and a later unguarded handler can return2^53. In particular, `JSON.parse("9007199254740993") - 9007199254740992` yields0, although the exact integer-token difference is1. Post-handler scanning cannot reconstruct that history.

Refusal is a bounded constant-message Error with a local reason code and **no data property**. The selected SDK forwards data to a typed ModelFailure decoder, so arbitrary validator data must not be attached. Do not catch refusal and silently Continue; do not automatically convert it into BlockTool. An error is not a universal guarantee that every host denies an underlying tool, and it does not roll back prior effects.

Native Rust integer representations or an explicitly reviewed lossless parser over retained raw text are alternatives with their own range/feature/provenance contracts. Raw text is not automatically the effective approved args, and parsing it with ordinary JSON.parse repeats the precision problem.

## Optional existing-SDK integration

The `optional-sdk/` directory contains a bounded offline probe and Python controls. It requires a **separately provisioned trusted** Core source checkout with five exact SDK file hashes, a separately provisioned trusted Node binary with a caller-supplied expected hash, and POSIX pipe/selector semantics. There is no auto-download, dependency installation, third-party hook or CI workflow.

See [optional SDK instructions](optional-sdk/README.md). The protocol is explicitly hook/v6 over component v3, not inferred from package versions. Initialization imports the authored fixture; it is execution, not safe inspection of untrusted code. Minimal environment and hashes do not create OS isolation or authenticate a caller-selected binary.

## Evidence boundary

Historical unchanged helper inputs passed38 pure controls and13 authored hook calls plus initialization through the selected existing SDK: four precise unsafe-number refusals without error.data, two Continue responses, seven expected replacements including immediate recovery42 and the two known limitations. Two direct children reaped exit0; no Core, Rust SDK, provider or real tool was invoked. Independent raw-frame/type review confirmed those results; timing was not a benchmark.

This is summarized historical evidence, not a claim that the adapted optional probe/public package has passed. Publication readiness requires the retest checklist and independent package review; raw private execution receipts and workspace paths are not bundled.
