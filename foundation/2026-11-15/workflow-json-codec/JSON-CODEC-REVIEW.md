# Independent review: workflow JSON codec extraction

## Verdict

No source-level semantic or type blocker identified. This is a practical, narrowly scoped deletion: four explicit workflow dispatch methods remain, with only their identical typed JSON boundaries shared. No callback abstraction, macro, new schema, or workflow lifecycle policy is introduced.

Source-only acceptance, not a compile/test/runtime PASS. No project code, tests, formatter, compiler, dependencies, or provider execution was run. No production edits or publication by this reviewer.

## Equivalence checks

1. **Malformed input:** each method first calls `decode_input(&input_json)?`; that helper invokes the same `serde_json::from_str` with the same concrete WorkflowModuleInput type. `&String` coerces to the same string slice previously obtained by `.as_str()`. Parse/schema failure returns before the run function can use the host. No default input, permissive Value intermediate, or schema adjustment appears.
2. **Decode/encode failures:** both helpers build `WorkflowFailure::new(error.to_string())`, exactly as the removed workflow_err helper did. Error text and absence of history/model_failure therefore remain the same for serde failures.
3. **Existing WorkflowFailure:** single-loop, Codex and plan/execute/review run functions return WorkflowFailure. `?` propagates that owned value through the identity From conversion rather than stringifying or reconstructing it. Its message, history, and model_failure are preserved. No helper wraps run errors with WorkflowFailure::new.
4. **ProjectCheck conversion:** run_project_check returns ProcessModuleError. The old `.into()` and new `?` select the same `From<ProcessModuleError> for WorkflowFailure`. The inspected Core implementation moves message and model_failure and sets history=None. This preserves existing behavior; it does not add project-check failure-history recovery.
5. **Output bytes/schema:** all four success paths still serialize the same owned WorkflowModuleOutput by reference with `serde_json::to_string`, then return its String. The concrete output type, serde attributes, order of serialization relative to execution, and error mapping are unchanged. No JSON parse/re-encode layer or map normalization is added. Removing String::from(String) in the first three methods removes an identity conversion, not formatting or encoding.
6. **Dispatch and side effects:** all four run_* calls and their arguments remain explicit and unchanged, including max_tool_rounds and CODEX_LOOP_MODULE_ID. There is one dispatch after successful decode and one serialization after successful dispatch. No retry, duplicate host call, new checkpoint, or response transformation was introduced.
7. **Type inspection:** WorkflowModuleOutput is publicly available in the same process_module namespace already used for input/host/trait. Helper signatures fix serde type inference; no borrowed input escapes. This was inspected, not compiled.

## Independent measurement

Text-only counts reproduce MEASUREMENTS.json:

| Metric | Before | After | Reduction |
|---|---:|---:|---:|
| Raw lines | 113 | 83 | 30 |
| Nonblank lines | 100 | 73 | 27 |
| serde_json::from_str sites | 4 | 1 | 3 |
| serde_json::to_string sites | 4 | 1 | 3 |

Both new helpers and the expanded import are included. This is source deletion and reduction in duplicated boundary code, not measured runtime speed, allocation savings, binary size, or proven maintenance savings.

## Scope and risks

The explicit four dispatch methods should remain explicit; further unification would hide the meaningful ProjectCheck error-type distinction and workflow arguments without a demonstrated benefit. Shared codec edits will affect all four entry points, so future changes must preserve their common contract. Existing workflow correctness issues and serialization-failure history behavior are neither fixed nor worsened by this extraction based on the inspected diff.

PR106 touched different source files according to the coordinator's assignment; this review does not claim an integration build against a merged branch. Baseline library wiring was read, and signatures of the three WorkflowFailure-returning runners were checked in the earlier exact-pin source snapshot. Fresh-head and full blob verification were supplied by the coordinator, not independently repeated.

## Evidence

Modules baseline `c035142558f0fca43e9772fc0e50ca293abf1531`; Core `bcbda4435534a296c707a1daa250813d692f68e1`. Read before/after workflows.rs, full patch, library wiring, project_check signature and Core WorkflowModuleInput/Output/trait, WorkflowFailure and ProcessModuleError conversion. Exact source blobs are catalogued in SOURCES.json; baseline workflows.rs blob is `d5aceb6ddf49970c16698634ea4738fa04ca0ee1`.

- Before workflows.rs SHA256: `396c3b2a2612d810fb26733024a9eb21e7ec98307eb9c333f23904571dccb3b5`
- Reviewed after workflows.rs SHA256: `c437d980b9170b1f1ef45c3339bb09f8048b57c7687a83ae491370a8f211f41e`
