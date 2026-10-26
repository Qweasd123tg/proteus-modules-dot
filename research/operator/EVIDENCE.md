# Evidence identities и публичные source references

Здесь указаны идентичности ранее принятых scoped artifacts, а не ссылки на якобы уже опубликованные отчёты. Полный SHA-256 сохраняет provenance; он не аутентифицирует источник и не заменяет содержательный review. Linked primary sources закреплены commit-ом. Runtime evidence имеет отдельный scope; этот public-copy пакет не выполнялся.

## e01

**R28: Wasm/process boundary**. Разделы: W01–W08; smallest context_provider/v4 consumer.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `Wasmtime50 ebe5e8df1f4e12c5fc2f5954926881d8d61367d8`; `Extism1.41 051b765bb6abe4fe95d5e4f489f03ad7b137edbc; dependency requests Wasmtime49, unbuilt`.

- Artifact `E01:REPORT.md`, SHA-256 `4022128abc004cde7a04a58f03f57dc3935176c93514a5a471b8c0b8027f371f`.
- Artifact `E01:SOURCE_PINS.json`, SHA-256 `992823198d23d8d8d726e87e691cc677dda1b1cd0e292ac426f90ae66c73bfba`.
- Artifact `E01:FILES.sha256`, SHA-256 `f7e6e17a9e51abece65688ba10d3b34faf97c023cfc55da0befc8fd51920608a`.
- Artifact `E01:wasm-boundary-source-review.json`, SHA-256 `0d50b05f0d3b8d781db83769dabeaf99f82c5cd6e14df17c0e5926c2eec9c3c4`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-process-host/src/sandbox.rs)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-process-host/src/sandbox_linux.rs)
- [Pinned source 3](https://github.com/bytecodealliance/wasmtime/blob/ebe5e8df1f4e12c5fc2f5954926881d8d61367d8/crates/wasmtime/src/runtime/limits.rs)
- [Pinned source 4](https://github.com/extism/extism/blob/051b765bb6abe4fe95d5e4f489f03ad7b137edbc/runtime/src/plugin.rs)

## e02

**R48: common SDK hook wire**. Разделы: SDK-01,02,04,06,07,08.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `Modules04114bbe85f179895e2b8553b6169a284caaeae3; selected SDK files equal bee0/3f/1fc, not full graph`.

- Artifact `E02:REPORT.md`, SHA-256 `b2f46cf8d8aa3f7c17748ae448e7f48b2a140ca2b87a575e74a081320dd514a3`.
- Artifact `E02:SOURCE_PINS.json`, SHA-256 `b13d563e97e359b4b968dd6c71e3d48be8d5acdfb6ac041d8232637b8e31bc26`.
- Artifact `E02:FILES.sha256`, SHA-256 `32849b4f2fdff128bc3422e7c549c41085142a53cf6906e59e8faf41948a639e`.
- Artifact `E02:sdk-wire-source-review.json`, SHA-256 `5fa6b0f5507266ffb1e7d34eb5d2d38a16e10fba50602afbeaeb0e537b09251a`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-module-protocol/src/v3/routing.rs)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/extension_operations.rs)
- [Pinned source 3](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/examples/modules/hook-process/worker.mjs)

## e03

**R37: portability**. Разделы: Process-host matrix; framing/deadlines; no cross-OS execution.

Pins/scope: `CoreA 3f36a003b4f3fde2242fc80f7aedac00dd127d1d`; `CoreB 1fc3ef223d10322815dd9290a50d045bc95402bb; 15/16 selected file pairs equal`.

- Artifact `E03:PORTABILITY.md`, SHA-256 `c2c5d8f0ccc5dd912e4fc29736a723612a2f4d9e04c09e3881d515b1399bc60b`.
- Artifact `E03:SOURCE-AUDIT.json`, SHA-256 `25825231c95c16f0e1351c1079241440ca79d71fb9befb4fc4ba670aea2e902e`.
- Artifact `E03:SOURCE-SNAPSHOT.json`, SHA-256 `3d4655e68e9ec81d6a0e8452a5efb3d76f7f34a7ff84928e098b5be5e72a238e`.
- Artifact `E03:portability-source-review.json`, SHA-256 `3088b91e41add056cc8d152b15772847a7ff4eaa8f18a15684b4d88b45b532f0`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-process-host/src/launch.rs)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-process-host/src/lifecycle.rs)
- [Pinned source 3](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-process-host/src/sandbox.rs)

## e04

**R21: protocol authority boundaries**. Разделы: §2 capability matrix; §3 actual consumers; §4 adapter proposals.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `A2A1.0.1 3303592588e388e62e0f69f701af531d2f4e3991`; `ACP66ff8076ec2320d85e84fedc83cb779e9d906a89; AG-UI082bf3ada3ef5f287ff50db3237b90ef7fb023fc`.

- Artifact `E04:REPORT.md`, SHA-256 `10b745dd6dd7f8c06f3049eaf39d510fa040bc8b550b9efa4f1d160a0b923152`.
- Artifact `E04:SOURCE_PINS.json`, SHA-256 `a5f9333048a838924eab909acc8c0a76cb8fb17629382b622acbce9c134101d9`.
- Artifact `E04:FILES.sha256`, SHA-256 `3c859bc49b9878bee51a7d489369c0e89795091ba8d51410222dd3e7de995519`.
- Artifact `E04:protocol-matrix-source-review-manifest.json`, SHA-256 `7930181fb1a7920ba4f8d39623d01bef5032d48f6f04767ee8bfed7c3cb611b3`.

- [Pinned source 1](https://github.com/a2aproject/A2A/blob/3303592588e388e62e0f69f701af531d2f4e3991/docs/specification.md)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/acp/mod.rs)

## e05

**Accepted adoption guide + R25 ACP directional boundary**. Разделы: Guide §3–4 and shortcuts; ACP-Z01,Z06,Z07.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `Zed8dd255c3eafb5231056fe4e6f601cedd011f1c93; external ACP wireV1, no matched runtime`.

- Artifact `E05:ADOPTION.md`, SHA-256 `90c69b01a248159bc0cd1fa855fcf56c90081c35f554107f9c7ed0f3582bc480`.
- Artifact `E05:PROVENANCE.json`, SHA-256 `c5a063f9851cec803812c6d1258379df05738e6cc5df7386229a958643b0b204`.
- Artifact `E05:FILES.sha256`, SHA-256 `9eb0cf61498585c43c5e2c92824d85a11cb2283481e8298cdf36e7a2cbcacd5e`.
- Artifact `E05:interoperability-adoption-review.json`, SHA-256 `86be59f9bcb65ba65beff068f8fc4ff938036a2efe577fbca53c60e63df9e303`.
- Artifact `E05:REPORT.md`, SHA-256 `3cff6d3cde9e21939724cabd7644b2553b9ec77f16a64a00df7e61eb071e700d`.
- Artifact `E05:SOURCE_PINS.json`, SHA-256 `0b0d89d59efb8256688aed3cb18c5c8ff3fddaa36f44a20d903771d4eabe39e9`.
- Artifact `E05:acp-editor-source-review-manifest.json`, SHA-256 `b030288e19abf5254134a097136ead4aea608298349c5ba0e6c78fa049d0a9ce`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/acp/prompt.rs)
- [Pinned source 2](https://github.com/zed-industries/zed/blob/8dd255c3eafb5231056fe4e6f601cedd011f1c93/crates/agent_servers/src/acp.rs#L1026-L1034)

## e06

**R45: actual narrow numeric counterexample**. Разделы: RESULT controls/custody; not Core or sandbox execution.

Pins/scope: `Pinned Node previously identified24.19.0; five SDK files equal bee0/3f/current1fc; exact hashes in EVIDENCE.json`.

- Artifact `E06:RESULT.md`, SHA-256 `8ace413a3ef128fde48aba4f2948870c5bcdcd1257d6154b194228f5db7197b0`.
- Artifact `E06:EVIDENCE.json`, SHA-256 `4f81f659dbffaef68c7b801c28972d19eb67aceb4cde92d011033325b718fb85`.
- Artifact `E06:FILES.sha256`, SHA-256 `68e744fecb5e4e727607a2996e1b131c8d4ed2b8c9555fefbdef2b6807d074dd`.
- Artifact `E06:artifact-manifest.json`, SHA-256 `5f9218129f045ab07a88987eba7f52f64157139bd81a794a1ea842ef234eab94`.
- Artifact `E06:numeric-gate-runtime-review.json`, SHA-256 `34b229768d653c50e4833d56bd10f21bd88d06e858dff7c4c6b74aacef34cdf0`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/examples/modules/hook-process/worker.mjs)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/examples/modules/hook-process/hooks.mjs)

## e07

**R20: admission/effect/settlement**. Разделы: Proteus persistent bound path; raw/effect meaning; lost ACK.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb; no foreign reference implementation claims imported into this matrix`.

- Artifact `E07:REPORT.md`, SHA-256 `e480584bf93b06ebeb0a49309ff879a1215fb234dd10423943f6d183c68eac8e`.
- Artifact `E07:OUTCOME-STATE-MANIFEST.json`, SHA-256 `e25c213b9c6935cf51fcd488e18916c5d8062fa21851686f5df14e2d64e9bc3e`.
- Artifact `E07:outcome-state-source-review-manifest.json`, SHA-256 `cc24edf99a27aeb726d3959bcde67516dad989b6445c771c0d104aedf94646aa`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/bound_tools/hooks.rs#L92-L131)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/storage/append.rs#L45-L143)
- [Pinned source 3](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/runs.rs#L79-L177)

## e08

**R56: actual recovery read surfaces**. Разделы: RUNBOOK A–F; READ-SURFACES library/presentation boundary.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`.

- Artifact `E08:RUNBOOK.md`, SHA-256 `8aa73b02c8b851af339773e0104b073c7051e57727d2072485d15cba3374d9c4`.
- Artifact `E08:READ-SURFACES.md`, SHA-256 `ad2dc6ea66257e6884acab7f716b4f04d61ebacb572b1df1584da14f24e6e626`.
- Artifact `E08:SOURCE-RECEIPT.json`, SHA-256 `c5f80460af984b302e03a7b48293580bc38e57fbb21e4f7b90a76d6844948d6d`.
- Artifact `E08:recovery-runbook-source-review.json`, SHA-256 `3a543ae8bdb20e6a44413815096d8883af17346e5eecfa76785ab40f38dd6c96`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/http/analysis.rs#L218-L225)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/session_journal/projection.rs#L343-L395)

## e09

**R47: composed budgets**. Разделы: Evidence conclusion; process admission/callback lifecycle; practical consumers.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `Modules7fceaebc3bed8add9b0e3091110f59deca86ba46; conditional source composition, no integration run`.

- Artifact `E09:REPORT.md`, SHA-256 `c2286358566555363a243651a5ba1400852e62ae39c113656f0743c4e84d72fb`.
- Artifact `E09:COMPOSED-BUDGET-MANIFEST.json`, SHA-256 `47e6b29fde81dc48fbb2418ef0f7ec4797b5d92174bbe299075ae662efd34f18`.
- Artifact `E09:composed-budget-source-review.json`, SHA-256 `652432fa5a7d06f1a4db8e5719fd91fbc805bd7c817a4bb316340bc8a88d5b88`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-module-protocol/src/v3/runtime.rs#L237-L365)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/reviewed_workflow.rs#L44-L168)

## e10

**R36: evaluation layers**. Разделы: Core eval/replay/task-objective distinctions.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb; no new benchmark or Core execution`.

- Artifact `E10:REPORT.md`, SHA-256 `c1612761a03ac3a41a06ad50c570b27ea92405bb1a6a6fe9bd4005db8b692a18`.
- Artifact `E10:EVALUATION-QUALITY-MANIFEST.json`, SHA-256 `8f7ffb030786383805cae406f6a4be0882e3bd8dae71077263ceb45c6872e6f4`.
- Artifact `E10:evaluation-quality-source-review.json`, SHA-256 `1aa8935913e21bb71581b16733bd677fb0a0587b2427a8e416c6307b058f5aca`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/eval_report.rs#L38-L44)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/cli_workflow_replay.rs)

## e11

**R49: observability with mandatory queue supplement**. Разделы: Five planes; collection/delivery; OPERATIONS; item-count-not-byte-bound supplement.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`; `OpenAI Agents Python0.24.0 17d994bd3045dae71acda676a4ef4762ed8ecd94; not all framework telemetry`.

- Artifact `E11:REPORT.md`, SHA-256 `3de906dfcdd400f822f210ea483535febcabd2848ad58acb4034649bce9a6615`.
- Artifact `E11:OPERATIONS.md`, SHA-256 `ca6afc8ca2f6fa8cfb38a2dbc378fb423900ce7147a00443d157806b6ff012a9`.
- Artifact `E11:FOLLOWUP-QUEUE-BOUND.md`, SHA-256 `7044b8b6836c4449d5bc536de78b80738620c6bd2ea9e68c1a7bbc1399d30f47`.
- Artifact `E11:SOURCE-RECEIPT.json`, SHA-256 `b4515b87aeb06a9d63c4dab600f66cac415af4b708a4e915b930553cb566ec92`.
- Artifact `E11:FOLLOWUP-QUEUE-BOUND-RECEIPT.json`, SHA-256 `e511b901d3392fd7ff0f01de6c6aef90e2c3b546c9ce6d58a325fda0b332876f`.
- Artifact `E11:observability-source-review.json`, SHA-256 `3f6cd3803c688445f11eabe1bb90c759657fe9661c2777d46b05f0789c541ef3`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/event_store.rs)
- [Pinned source 2](https://github.com/openai/openai-agents-python/blob/17d994bd3045dae71acda676a4ef4762ed8ecd94/src/agents/tracing/processors.py#L705-L876)

## e12

**R40: effective configuration inspection**. Разделы: Inspection versus operational probes; policy is not sandbox; no config export.

Pins/scope: `Core 1fc3ef223d10322815dd9290a50d045bc95402bb`.

- Artifact `E12:CHECKLIST.md`, SHA-256 `cffc91d034d8e414d0e75258995bbe14d080f1ffb4ad4a47c1a0459e11919a60`.
- Artifact `E12:SOURCE-SNAPSHOT.json`, SHA-256 `d87baf51273b18e22f0d9bc16a6f7d6631bd1a7d4e32d394ef9791bd0652f891`.
- Artifact `E12:effective-config-source-review.json`, SHA-256 `638204f1b589a1e8147680dd08d00c3d49ce06b674073dbe1876e844e21a6cd1`.

- [Pinned source 1](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/main.rs#L102-L150)
- [Pinned source 2](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/cli_commands/dispatch.rs)
- [Pinned source 3](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/app_server/config_summary.rs#L148-L172)

## r39

Отдельный report classifier **не включён** в этот пакет и не является встроенной Core command. Применять его documented shape можно лишь к отдельно полученному и проверенному artifact; это не инструкция загрузки/установки. Поддерживает только Core1fc WorkflowReplayReport schema1; primary transport/execution/objective/evaluator state остаются unknown, observed status — reported-only. Exit0 означает доставку classification, не task success. Historical54 pure controls+3 synthetic CLI не являются Core producer run.

- Artifact `R39:REPORT-CLASSIFIER-MANIFEST`, SHA-256 `a89d2d45a8235ec2d2b6aa1c2aeb537f6bf0de1f8a43c0b547911551221973e3`.
- Artifact `R39:independent-review`, SHA-256 `776ec7373f1a20051f2779966ccc8be72aae35443e86bb9da35c0a931759ed5a`.
- [Pinned actual report type](https://github.com/Proteus-harness/Proteus-core/blob/1fc3ef223d10322815dd9290a50d045bc95402bb/crates/proteus-core/src/core/workflow_replay/report.rs).

## research-composition

Историческая source-only композиция AgentScope/Proteus, artifact `COMPOSITION.md` SHA-256 `f95471bbbecb20762d4095a3350a9941546e0bc9d41d69b3284cab3df94984a5`; не runtime авторизация. Конкретные current-Core механизмы и ограничения рецепта закреплены в его [SOURCES](research-team/SOURCES.md).

## r57

Narrow observed enforcement в guard-enabled authored fixtures, не broad deployment/полная numeric fidelity. Independent runtime review SHA-256 `f34d912a2904a47cd20b1288f2a2d624d7bd4633fd473e5007a358b0bbf7ee52`; artifact manifest `975cc8e0780371ed0264745c9ada73ed07f3c5b99f4c13c4330ac2b9833d9e1f`; helper manifest `09e3897f028f6abac4d10a2c7c632df0dd9b81b675edf58678930d1e62d0c570`. Обязательные limitations сохранены в [scoped supplement](extension-boundaries/OBSERVED-GUARD-LIMITS.md).

