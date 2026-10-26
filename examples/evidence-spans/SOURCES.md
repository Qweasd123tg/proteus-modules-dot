# Source pins and reused boundary

## Published build baseline

- Proteus SDK/Core: `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.
  [ToolExport/tool-v6](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-sdk/src/tool.rs),
  [ToolHostBridge](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-module-sdk/src/hosts.rs#L82-L123),
  [raw effect and AfterTool boundary](https://github.com/Proteus-harness/Proteus-core/blob/3f36a003b4f3fde2242fc80f7aedac00dd127d1d/crates/proteus-core/src/core/bound_tools/hooks.rs#L92-L130).
- SHA256 implementation: ring0.17.14, same dependency pin as existing authored verification example; no custom crypto.

## Exact supported reader convention

Core3f repositories.json selects Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46`.
[tool/file-tools/src/read.rs](https://github.com/Proteus-harness/Proteus-modules/blob/7fceaebc3bed8add9b0e3091110f59deca86ba46/tool/file-tools/src/read.rs): Git blob `7cb16cfbc2f014200aa38902b89dd0adcd74b720`, SHA256 `c5e2e34a158b5eaa35a05ad65debb789ec63ffc613f8e23ecd26e07d58e4e6df`.

Read-only comparison established the same bytes at Modules `04114bbe85f179895e2b8553b6169a284caaeae3`. The full Modules7f package still pins SDK `bee0e409e746e2df9db32748d4f8ea02201bd4af`: **source convention equality is not proof of full-pack build/runtime compatibility**. This example invokes a host-registered reader; it does not link that pack or supply a substitute filesystem reader.

Pure checked-read validator was factored from the authored JSON-contract producer's read-boundary logic with its owner's coordination. It adds explicit output-limit parameter, preserves typed metadata/null rejection and does not import the producer implementation or JSON assertion code. Other JSON-contract consumers are unchanged; any eventual shared-support adoption needs both consumers' regression tests.

## Current source baseline kept separate

Current local Core source `1fc3ef223d10322815dd9290a50d045bc95402bb` was read. ToolModule SDK, HostBridge, canonical ToolResult/ToolContext/ConversationView and relevant BoundTools files are byte-identical to3f. In all contracts+SDK the diff is only three added lines for SessionCatalogUpdated app event. This establishes source comparison for the narrow boundary, not current-Core execution. CI builds the pinned3f SDK only; the current-source comparison is informational and not current-Core runtime validation.

## Research motivation, not copied runtime

[OpenHands action/observation separation](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/event/llm_convertible/observation.py#L17-L72) and
[view projection](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/context/view/view.py#L74-L160)
show why rendered context is not raw evidence. The tool here audits exact local bytes rather than replaying foreign events or actions. No upstream code imported/executed. All fixture texts and boundary tests are authored for this module.
