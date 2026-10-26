# Статусы: проверенный пример ≠ полный runtime

Срез26 октября2026,02:18UTC; последующая редакционная адаптация не обновляет runtime-статусы. Это сводка существующих receipts, **не новый запуск**. Не суммируем разные тесты в один pass count и не называем объединение sibling branches tested release. Exact hashes входов — [INPUTS.json](INPUTS.json).

Обязательные уточнения: [точный слой CAS wire tests](FOLLOWUP-CAS-WIRE-LAYER.md) и [LiveKit completed не означает полную озвучку](FOLLOWUP-REPLY-STATUS.md).

## A. Примеры с выполненными ограниченными проверками

| Артефакт | Наблюдённый слой | Не доказано |
|---|---|---|
| [PR1 Pi/Letta/Hermes v1,29d31fb](https://github.com/Qweasd123tg/proteus-modules-dot/tree/29d31fb36397008b7677cd5df4943031e24e8fdf/examples) | Authored policy/wire tests; отдельно [PR3,d6ec511](https://github.com/Qweasd123tg/proteus-modules-dot/tree/d6ec511febbda5b2a298f25acc7f7e607fb4a4a3/integration/core-smoke) с21 model-free actual-Core checks выбранных boundaries | Полный agent turn, currentCore compatibility, official reference reader deployment, truth supplied statuses/blocks |
| Pi existing-binary supplement R23 |4086 tool invocations +2setup=4088RPC;4013 successful outputs и73 exact negatives независимо перепроверены по retained artifacts | Реальный DAG executor, historical status truth, concurrency/cancel settlement, Core/provider |
| Letta existing-binary supplement R26 |398 requests/98direct children;295 complete projections,4RPC errors,6paired factory errors иnull catalog сверены независимым readback | Persistent mutable memory, authenticated provenance, prompt-injection protection, Core/model |
| Hermes v1 existing-binary supplement R27 |909 hook cases +5init=914RPC;101Continue/793nudge/15errors, independently derived outputs/raw frames/pins | Authenticated Core history, actual verifier/effects, strict-v2 suite coverage; Continue не означает verified project |
| [Strict JSON + Hermes v2,056c8ded](https://github.com/Qweasd123tg/proteus-modules-dot/tree/056c8ded32f36352ca846d4b3ce807359e32db38/experiments/strict-pair) |81+8Rust cases, отдельные18 artifact controls; producer/consumer, own processes, synthetic reader/history | Actual full Core turn/approval/official reader. V1/v2 receipt generations не взаимозаменяемы |
| [Portable skills,592ad5ca](https://github.com/Qweasd123tg/proteus-modules-dot/tree/592ad5cab6ab35fa181756a42607a32a696d9ccd/examples/portable-skill-catalog) |29 behavior +1own-wire case; bounded catalog/load | Core pair11 ещё unrun; imported allowed-tools не grant и не script activation |
| [Claude command hooks,fdcd5687](https://github.com/Qweasd123tg/proteus-modules-dot/tree/fdcd5687a5a510732396d1c0bc0b9a0cc61d821a/hook/claude-command-hooks) |33 authored adapter/SDK controls | Полная совместимость Claude, foreign hook execution, OS sandbox; запуск hook требует собственной авторизации |

R23/R26/R27 — последующие локальные supplement, не переписанные старые README или публичные CI counts. Их факты ограничены данным binary/source/corpus. Review acceptance: R23 SHA3397fcdb0b6bb1cbf6e635f294fb2cbd1c12c7bf5d8f85d8cf1db83bad39c571; R26 SHA8ad452f6d99c39ca115faa7b5621697f826071faaa8961142793f8d7d13c5e22. R27 acceptance SHAa25069faa759ba2874d99ae7ecefef592a15d6ae1ef0d07693d9ae348a4102f8. Reviewer выполнил независимый artifact readback, не повторный запуск бинарей.

## B. Исполненные проверки, которые не являются новым installed module

- [rmcp lifecycle,f464bdc1](https://github.com/Qweasd123tg/proteus-modules-dot/tree/f464bdc1ef914c617cafd43070cf04e6b15c0e7e/conformance/rmcp-lifecycle):33 authored pinned-SDK cases. Это conformance probe, не Core MCP registry/approval pass.
- [Native cache,5901a601](https://github.com/Qweasd123tg/proteus-modules-dot/tree/5901a6013a4578d38a1e8afd65daf2a207eaed09/conformance/native-read-cache): actual Core1fc owned temporary-data/cache/read observations и bounded measurements. Не causal production speedup и не resume authority.
- Static module-preflight v2:62 pure controls +3CLI, corrected schema2. Различает raw wire version `vN` и qualified contract `slot/vN`; не запускает module initialize. Старый R19 frozen label нельзя копировать в initialize JSON.

## C. Source-only prototypes — не «почти прошедший runtime»

| Прототип | Точный статус | Следующая граница |
|---|---|---|
| evidence.verify_spans R11 | Source-ready,39Rust cases uncompiled/unrun; source receipt88e961…; lock/metadata/fmt only | Exact-source tests и отдельный actual Core/reader integration; witnesses не entailment/origin proof |
| Usage attribution R18 | Source-ready,37Rust cases uncompiled/unrun; source receipt24591872…; static fixture math не Rust execution | Pure runtime/own stdin tests; actual transport caller-owned, owner/attempt/cost unavailable |
| Correction memory R17 | Historical source-ready58unrun; frozen0ba3a385…; no lock, missing rusqlite | Source compatibility erratum: valid raw arguments были отвергнуты после SDK normalization |
| Correction memory raw-compat | Separate candidate69unrun,7e5d2fd3…; independent source-readiness accepted; runtime pending | Lock/dependencies, real SQLite/module pairing/restart tests, затем отдельный Core boundary |
| Strict full host | Source-ready authored harness/model;8actualCore cases,5live cleanup controls,16fixtureRust unrun | Нельзя наследовать green из standalone strict pair |
| Core skills pair |11planned actualCore cases unrun | Наличие branch на portable base не означает опубликованную Core implementation |

R17 four actual-module pairing cases и3wire-file cases входят в58: **2own-binary (restart/cancellation) +1pure framing helper; все uncompiled/unrun**. Новый69-test candidate включает старые58+11, не69дополнительных. R11 source witness не становится универсальным Hermes receipt, а CAS durable replay не обещает свежую повторную проверку источника.

## D. Только proposals/configuration patterns

Round7 reader/reviewer composition, Round8 text voice bridge, route/context corpus, recovery inspector, observation-bound browser driver, durable review inbox иowner-aware usage exporter — **design/source-only**. Не installed, не runtime-tested. Native media, external actions иremote deployment не разрешаются этим roadmap.

## Версии и corrections

- Authored Rust examples SDK/Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`; source comparison Core `1fc3ef223d10322815dd9290a50d045bc95402bb`. Source equality выбранных файлов не равна общей runtime совместимости или одинаковой Rust package identity.
- Official Modules `7fceaebc3bed8add9b0e3091110f59deca86ba46` имеет собственный SDK `bee0e409…`; legacy profiles `04114bbe…` — иной pin. Полный reference startup не подтверждён.
- [Round6 follow-up usage](SOURCE-ARTIFACTS.md#clarifications): R18 не содержит owner и не требует нового journal exporter. [Cancellation erratum](SOURCE-ARTIFACTS.md#clarifications):500msCore grace — cooperative nominal asynchronous wait, не hard preemption/OS effect rollback.
- Предыдущая архитектурная заметка — planning input, а не техническое доказательство; её прежнее «correction memory проектируется» исторично. Здесь учтены separate source implementation и последующий compatibility candidate; исходный документ не изменён.
- Accepted install/navigation guides помогают выбрать pin/slot/profile, но не являются разрешением запуска или production certificate. Public main не следует считать объединённым package delivery.
