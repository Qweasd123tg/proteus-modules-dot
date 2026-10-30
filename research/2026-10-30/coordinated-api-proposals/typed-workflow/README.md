# Typed WorkflowModule: согласованный alpha Rust API proposal

**Не drop-in patch.** Текущий Modules Core pin —
`1f533a13f20a93bf164f7c8a169553b0b219bb51`. Modules patch с этим прежним API
несовместим; fake revision и ручного lockfile здесь нет.

## Единственный путь

[Core patch](patches/core/01-typed-workflow-helper.patch) заменяет существующий
`WorkflowModule::run_json` на typed `run` с owned `WorkflowModuleInput` и
`WorkflowModuleOutput`. [Modules patch](patches/modules/01-typed-workflow-helper.patch)
переводит одну production invocation, четыре реализации и 48 test callers.
Реализации вызывают уже существующие typed algorithms. Runtime по-прежнему
обращается к общему trait object, а не связывается с конкретной реализацией.
Старого helper, обходного dispatcher и параллельной compatibility ветки нет.

Из внутреннего invocation убраны две text serialization и две text parsing
стадии. Actual process wire и `WorkflowModuleHost` JSON callbacks остаются;
это не IPC encode-once и не измеренное ускорение.

## Deliberate normalization/error migration

| Граница | До изменения | После изменения |
|---|---|---|
| Process input decode | Strict `from_value<ProcessWorkflowInput>`; transport error | Без изменения, до helper invocation |
| Helper input | `to_string` мог дать transport error; producer `from_str` — synthetic `WorkflowFailure` | Owned typed input; обе serde стадии удалены |
| Algorithm failure | `WorkflowFailure` с explicit history/model cause | Без изменения; project-check сохраняет прежний From mapping |
| Helper output | Producer `to_string` мог дать synthetic `WorkflowFailure`; runtime `from_str` — transport error | Typed output; обе serde стадии удалены |
| Process response encode | `to_value`; transport error | Та же граница; теперь сюда доходят typed output encoding failures |
| Actual wire parser/writer | Собственные limits/serde/error rules | Без изменения |

- Deep `Value` больше не отвергается промежуточным text parser; actual wire
  parser всё ещё может его отвергнуть. Regression source фиксирует обе стороны.
- Rust `Some(NaN/±infinity)` в optional score больше не нормализуется до `None`
  между helper calls; на JSON boundary serde по-прежнему кодирует `null`.
  Это не разрешение принимать domain-invalid history.
- Не-UTF-8 `PathBuf` в typed output теперь даёт transport encoding error,
  а не synthetic algorithm failure. Typed input также не проходит прежнюю
  helper serialization; actual wire input обязан пройти wire/DTO boundary.
- `None` и `Some([])` history replacement различаются как прежде. DTO strict
  fields, serde defaults и required nullable runtime fields не ослаблены;
  typed construction просто не вызывает deserializer. Diagnostics удалённого
  text parsing, включая line/column, намеренно не обещаются.

## Сохранённые authority и failure boundaries

Dispatch сначала проверяет `process_contract_authority` и метод, выбирает только
bound module id и создаёт тот же `WorkflowHostBridge`. Config остаётся
binding-owned, а не входным полем. SDK invocation identity, policy, fresh
tool/model validation, cancellation, callback error data и cross-export routing
не меняются. Algorithms, scaffold, preparation, checkpoint ACK/revision и Core
journal validators не меняются. Explicit failure history сохраняется; новая
transport ошибка не изобретает rollback. Durable checkpoint остаётся authoritative.

Три Core characterization regression sources и шесть Modules adapter regression
sources включены в patches. Они покрывают normalization, defaults, replacement,
diagnostics, owned input/config, strict process decode, failure history/model cause,
deep output и unencodable path. Это **исходники тестов, не результаты выполнения**.

## Caller inventory и pinned sources

[SOURCES.json](SOURCES.json) содержит identities всех изменяемых upstream файлов
и final candidate hashes. Новые файлы обозначены отсутствующим upstream blob,
а не ссылкой на несуществующий upstream файл.
[INVENTORY.json](INVENTORY.json) сохраняет публичные identities всех 594 Core и
259 Modules tracked Rust files, проверенных при caller inventory. Найдены четыре
producer implementations, одна production invocation, typed registrations и
48 test callers. Инвентаризация не покрывает произвольных внешних Rust consumers.

В Desktop `src/` и `crates/client-common/` на его закреплённой revision нет
`WorkflowModule`/`run_json` consumers: 269 source identities приведены в общем
[Desktop inventory](../contracts-runtime/DESKTOP-INVENTORY.json). Vendor/examples
не входят в этот Rust scope. Внешние workers, использующие только wire protocol,
не требуют этой Rust helper migration.

## Обязательная интеграция

1. Применить Core proposal к указанной Core base и получить **реальный доступный
   reviewed Core commit**. Integration owner проверяет delta от текущего Modules
   pin к выбранной revision. Обычно используется текущая линия Core.
2. Тот же Core patch статически применим к существующему Modules pin: helper blob
   идентичен, preimage guide проверен на pin, новый regression path отсутствует.
   Это только source compatibility evidence, не созданная альтернативная revision
   и не рекомендация перематывать upstream назад.
3. На Modules base применить Modules patch, согласованно обновить все пять
   dependencies (`proteus-module-sdk`, `proteus-contracts`, `proteus-module-protocol`,
   `proteus-process-host`, `proteus-core`) на этот реальный Core commit. Штатно
   регенерировать `Cargo.lock` в целевой среде сборки; вручную lockfile не менять.
4. По существующим guides выполнить полные Core/Modules Rust gates, `module_swap`,
   process conformance/independent-worker invocation, failure/recovery и все
   изменённые tests. SDK runtime validation обязательна и не выключается typed
   helper migration. Проверить внешних Rust consumers выбранной alpha revision.

Canonical architecture guide и Modules reference обновляются **в самих patches**,
без нового общего framework или дублирования правил. Exact current dependency
entries и pending gates: [DEPENDENCIES.json](../DEPENDENCIES.json).

## Проверено и не проверено

[VALIDATION.json](VALIDATION.json) разделяет source/application checks и pending
executable gates; [COMPOSITION.json](../COMPOSITION.json) задаёт точные варианты
совмещения. Fresh-base patch hashes: Core `9c06f6b6…`, Modules `916c2adc…`;
полные значения — [SHA256SUMS](SHA256SUMS). Standalone forward application,
candidate equality и exact reverse проверены. Прямой installed rustfmt проверил
17 изменённых/новых Rust files; это parse/format evidence, не compilation.

**Открыто:** реальный Core commit → Modules pins/lock → executable validation.
Upstream writes не выполнялись. Proposal не готов к merge и не обещает работу
при прежнем Modules pin.
