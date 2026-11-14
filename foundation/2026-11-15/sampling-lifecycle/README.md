# Non-streaming sampling lifecycle: measured simplification candidate

## Решение

**Один конкретный source-only refactor candidate, не новая bug finding.** В `coding.single_loop` и `coding.plan_execute_review` пять копий одного lifecycle сведены к одному небольшому `sample_step` helper. Изменены только изолированные candidate files; upstream/production/Git refs не тронуты.

Независимый review не обнаружил semantic blocker при чтении. Это **не** compiler/test/runtime verification, не merge-ready patch и не обещание полной observational equivalence.

Свежо проверенная база: Modules `c035142558f0fca43e9772fc0e50ca293abf1531`; Core main `bcbda4435534a296c707a1daa250813d692f68e1`. Patch относится к raw Modules SHA, не к произвольному checkout с ранее опубликованными patches.

## Измеримый результат

| Участок | До | После | Δ строк |
|---|---:|---:|---:|
| single_loop.rs | 176 | 131 | −45 |
| plan_execute_review.rs | 277 | 206 | −71 |
| новый sampling.rs | 0 | 71 | +71 |
| lib.rs | 92 | 93 | +1 |
| **Всего affected source** | **545** | **501** | **−44** |

Непустые строки: **−46**. Unified diff: 166 removed / 122 added. Учитываются весь новый helper, config struct и module declaration; экономия не получена переносом удалённых строк за границу подсчёта. Это около 8% affected source, **не** всего crate.

В выбранных workflows плюс новом helper по source-text occurrence:
- `request_from_state`: 5 → 1;
- `apply_compaction_report`: 5 → 1;
- request-prepared event: 5 → 1;
- response-received event: 5 → 1;
- response validation: 5 → 1.

Польза: один owner порядка preparation/ACK/model invocation, а не пять мест для одинакового изменения. LOC и число копий измерены; снижение ошибок, runtime latency, allocations/RSS и developer time **не измерялись**.

## Что объединено, а что намеренно оставлено

Helper выполняет:
1. прежний `request_from_state` с прежними phase/system/developer/usage;
2. apply compaction с `PersistentRepair::Rebuild`;
3. при changed: invalidate last usage → checkpoint → adopt accepted `turn.model_messages`;
4. только затем, если нужно, запрет tool calling через literal `disable_tools`, без обещания nonempty text;
5. request event → existing complete_model (включая прежнюю usage telemetry) → response event → validation;
6. возврат response без изменения phase-specific response history.

В callers остаются:
- plan/execute/review sequencing и round budgets;
- private plan IDs/scope, execute draft handling;
- persistent/model history mutation и usage message_count;
- tool binding/execution/results и checkpoints;
- final output/metadata и failure wrapper.

Codex streaming, project_check, Pi/OpenCode, tool execution policies и Core contracts не включены в новый helper. Это extraction, а не общий workflow engine и не попытка объединить разные recovery модели.

## Пять вызовов

| Call site | Phase | Developer instruction | Disable tools |
|---|---|---|---|
| single normal | single_loop | None | false |
| single terminal | single_loop_final | None | true |
| plan | plan | PLAN_DEVELOPER_INSTRUCTIONS | plan_round == MAX_PLAN_TOOL_ROUNDS |
| execute | execute | EXECUTE_DEVELOPER_INSTRUCTIONS | false |
| review | review | REVIEW_DEVELOPER_INSTRUCTIONS | true |

System instruction строки остаются прежними для каждого workflow.

## Факты из source review и остаточные риски

**Проверено чтением:**
- rejected preparation по-прежнему не доходит до model request event/invocation;
- accepted checkpoint по-прежнему предшествует clone accepted messages в request;
- tool suppression не перенесён до tool selection/context preparation, поэтому их текущая семантика/estimate не изменяются;
- emit/complete/validate порядок и короткое замыкание `?` сохранены;
- Core `with_tool_choice` является простым присваиванием поля, поэтому замена на присваивание в helper не убирает скрытого side effect;
- computation `forced_text_round` перенесено раньше, но это только сравнение usize. Сам `request_from_state` **не pure**: он вызывает host capabilities;
- на final single/review compaction helper теперь также очищает last_usage. Раньше terminal branches её не очищали, но после этих branches значение больше не читается и не попадает в failure output. Это наблюдаемо инертное локальное отличие по прочитанному control flow, не обещание сохранения всех внутренних состояний.

**Не проверено:**
- Rust compilation, rustfmt/clippy и package tests;
- взаимодействие с реальными hooks/providers/host и timing;
- совместимость с delivery patches/reconstructed baseline, включая будущие правки затронутых workflows;
- бинарный размер/быстродействие.

Известные runtime-instructions/steering/cancellation findings не исправляются и не маскируются этим extraction. Phase configs остаются строковыми как раньше; new enum/framework ради эстетики не добавляется. Не следует расширять этот helper на Codex streaming только ради дальнейшего LOC.

## Gates перед применением

1. Применить к целевому checkout после выбранных functional fixes; проверить новый source diff и Core dependency pin.
2. Formatting + compilation + package tests. Existing source tests single_loop, plan_execute_review, preparation, failure_history и request_accounting прочитаны, но не запускались.
3. Focused trace regressions для всех пяти call sites: no-op preparation; changed preparation with ACK adopting modified history; checkpoint rejection without model call; forced-text after preparation; complete-model failure; validation failure.
4. Проверить request shape, event order/count, current usage/message_count, private plan persistence и failure history, не только final text.
5. До этих gates не объявлять готовым production упрощением.

## Артефакты и метод

[Candidate patch](sampling-lifecycle.patch), [полный LOC](LOC.json), [копии lifecycle и hashes](DUPLICATION.json), [независимый review](SAMPLING-REVIEW.md), [точные source identities](SOURCES.json).

12 исходных Git blobs сверены по сохранённым source identities. Перед публикацией повторно проверены remote main обоих upstream repositories и blob SHA трёх изменяемых Modules files. `git apply --check` прошёл на изолированной копии exact baseline; это только проверка применимости текста, не compilation. Patch SHA256: `d60add66d35fe7e8dd322cc38d794ca723ae03f649b4cf9d6ec5845b0bc66b5c`.

Код проекта, validators, tests, fixtures, builds, providers, runtime и installers не запускались. Зависимости не устанавливались. Здесь публикуются только отчёт, source identities, независимый review, измерения и candidate patch. Слияние этого пакета в delivery repository не применяет patch к upstream и не означает production readiness.
