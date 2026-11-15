# BeforeModel и model deadline: HOLD до выбора границы

## Итог

Это source-only follow-up известного PR85 hook-deadline, не новая finding и не повторный runtime reproduction. **Patch не подготовлен:** документация и явные тесты не выбирают однозначно, должен ли BeforeModel расходовать runtime.model_timeout_ms. Смена положения часов или blanket timeout поверх hook были бы сменой semantics, а не нейтральным упрощением.

Независимый reviewer также рекомендует HOLD. Узкое исправление возможно после выбора scope; новый framework не требуется. Здесь нет утверждения, что исправление принципиально невозможно.

Проверены Core main bcbda4435534a296c707a1daa250813d692f68e1, Modules main c035142558f0fca43e9772fc0e50ca293abf1531 и delivery main 89784350e214f5fbf5fa3eab473396b574d63653, включая PR124. PR119/124 относятся к отдельной file-read composition и остаются uncompiled proposals. Modules' actual Core dependency остаётся 41bdfffa6e70228278b4abc758b7f81a12672f35; этот pass анализирует host Core main, не притворяется его сборкой против Modules pin.

Проверены 18 exact Git blobs; каталог исходников приведён ниже. Сохранение полного файла не означает review всех его направлений: проверены только deadline/phase/cancellation-lineage/recording semantics и релевантные docs/tests. Никаких security/flagged механизмов не исследовалось.

## Что подтверждает текущий source

BoundModel::stream создаёт один deadline до вызова stream_with_deadline. Внутри последнего apply_before_model и model_request_recorded awaited до первого timeout select. RuntimeHookChain получает дочерний token от текущего operation/turn scope; отдельный BoundModel deadline этот token не сигналит. Поэтому время hook учитывается в часах будущего запроса, но само ожидание hook не ограничено этими часами.

| Фаза | Номинальный model deadline уже создан | Есть локальное ожидание этого deadline |
|---|---|---|
| Начальная подготовка и bind request | Да | Нет; синхронная часть |
| Чтение conversation snapshot и BeforeModel chain | Да | Нет в BoundModel; chain наблюдает operation/turn cancellation |
| Повторная подготовка и bind после hook | Да | Нет; синхронная часть |
| model_request_recorded | Да | Нет |
| service.start_prepared | Да | Да, один select с cancellation |
| Чтение provider stream, включая provider retry/backoff внутри него | Да | Да, тот же deadline |
| Live presentation await | Да | Да, тот же deadline; уже принятый terminal response не заменяется timeout |
| Terminal/error recording и cooperative settlement | Deadline может уже истечь | Не являются универсально ограниченным wall-clock возвратом |

Таблица показывает размещение проверок, не измеренную длительность. Документация обещает общий deadline запуска и stream, но из этого нельзя выводить hard wall-clock bound всех recorder/settlement awaits.

RuntimeHookChain сохраняет принятые contributions в локальном HookTrace. trace записывается после chain либо при принятом failure. Hook может законно выполнить model/tool callback; auxiliary model получает обычный собственный BoundModel deadline и не вызывает рекурсивный BeforeModel. Дочерний callback восстанавливает owner/lineage/cancellation родителя.

Это объясняет исторический сценарий с двумя успешными auxiliary calls и отклонённым до provider main request. Но новое измерение частоты, stock-hook incidence или реальный provider run здесь не проводились. Старые 11 process sessions описаны в [историческом отчёте PR85](../../../research/proteus-continuous-audit-2026-11-13/evidence/hook-deadline/REPORT.md) и относятся к прежнему Core89997df9/Modules3270dc0.

## Документация и явные controls не решают policy

- docs/guides/runtime-and-events.md:2286-2297 описывает один deadline для запуска запроса и чтения model stream, provider retry/backoff, модельную Error отдельно от внешних Canceled/Timeout.
- docs/guides/configuration.md:609-616 различает workflow budget, отдельный model call и explicit hook-export timeout.
- docs/architecture/hook-tool-operations.md:22-29 требует parent scope/budget для callbacks и сохраняет auxiliary journal/usage, но не определяет, включён ли сам BeforeModel в model budget.
- RuntimeConfig содержит число model_timeout_ms и default; выбора phase/start point там нет.

Девять bound_model_tests/deadline.rs controls проверяют start timeout, stream timeout, единый non-resetting deadline, zero disable, stalled sink, terminal response preservation и drop provider до error-record await. BeforeModel duration в них не задан. Прочитанные execution_hooks/extension_operations controls проверяют ordering, hook failures, cancellation, auxiliary origin/owner, но не выбирают эту временную границу.

Это source reading существующих тестов, не успешный запуск. Не заявляется exhaustive поиск любого мыслимого теста во всём repository.

## Почему две маленькие правки не нейтральны

### Перенести часы после hook

Это согласованный вариант, если выбран бюджет prepared-model phase. Он позволяет hook и его helpers использовать отдельный workflow/hook-export budget, затем даёт основному запросу новый model budget.

Однако перенос сразу после apply_before_model всё ещё включает model_request_recorded await. Назвать такой patch строгим provider-only wall-clock ограничением было бы неверно. Для действительно provider-phase start следует отдельно выбрать положение относительно записи request. Также нужно явно описать, что conversation read и request shaping до этой границы больше не расходуют модельный budget.

Никакая отдельная abstraction не нужна: можно развести подготовку и старт через существующие методы. Но это выбранное изменение scope, а не вывод из неоднозначного слова «call».

### Включить BeforeModel в единый operation budget

Это тоже согласованный вариант. Уже есть ExecutionScope::child_cancellation_scope и with_operation_scope: можно выразить invocation-local cancellation, сохранить ExecutionId, owner/lineage и не отменять sibling calls или весь turn.

Одного tokio timeout/drop вокруг apply_before_model недостаточно:
- dropping future не равен cooperative signal для captured callback tokens;
- принятые HookTrace steps ещё могут быть локальными;
- auxiliary exchanges или tool effects могли уже завершиться и не откатываются вместе с hook future;
- cancellation branch RuntimeHookChain предоставляет текущему handler до 500ms, затем пишет trace; внешний немедленный drop может обойти эту логику;
- durability await и settlement нельзя автоматически считать завершёнными к model deadline.

Нужен выбранный порядок signal, settle, сохранение accepted facts и ошибка внешнего call. Не подменять timeout подтверждением отсутствия effects. Не отменять общий scope ради одного модельного вызова.

Blanket timeout поверх всего complete дополнительно рискует нарушить явный terminal-response/stalled-sink control. Принятый и записанный Response не должен становиться новой ошибкой только из-за final presentation. Этот tested contract следует сохранить при любом выбранном варианте.

## Следующий полезный шаг

Выбрать явно одно:
1. Prepared-model/provider-phase budget, указав начало относительно BeforeModel и request journaling.
2. Full model-operation budget с локальным descendant cancellation и определённым settlement/trace поведением.

Затем минимальный patch и focused regressions без создания нового framework. До выбора HOLD сохраняет контракт честнее, чем перенос одной строки под видом общего исправления.

План controls, NOT IMPLEMENTED / NOT RUN:
- No hook/no-op hook, long cooperative BeforeModel, тот же BeforeContext.
- Один и два sequential auxiliary calls, сохранение их accepted records/usage.
- Deadline до provider start, во время provider start, в stream; continuous deltas не сбрасывают часы.
- Sibling model call остаётся активным после локального timeout.
- Cancel/workflow timeout сохраняют свои terminal kinds и приоритет при совпадении сигналов.
- Accepted hook steps перед поздним timeout, callback cancellation и settlement; отсутствие ложного rollback claim.
- Blocked request recorder и blocked terminal recorder как отдельные controls выбранной boundary, без заявления hard bound там, где он не выбран.
- Zero timeout, explicit hook-export timeout, accepted terminal response при stalled sink.

Новые tests не написаны и не запускались. Не выполнялись Rust/cargo/compiler/formatter/project scripts/provider/process fixtures/application runtime. Inert source hashing только проверяет identity. Production и upstream refs не менялись. Эта публикация содержит только документацию; patch отсутствует.

## Источники и независимая проверка

[Независимый source/design review](INDEPENDENT-REVIEW.md). Публикация не является исправлением или повторным воспроизведением.

- [crates/proteus-core/src/core/bound_model.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_model.rs) · Git blob f0a120ab2072507f9984054905023dddccf41cd1
- [crates/proteus-core/src/core/bound_model/hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_model/hooks.rs) · Git blob 3f7976beb75727731e1985c93c2c24cda25658b4
- [crates/proteus-core/src/core/bound_model_tests/deadline.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_model_tests/deadline.rs) · Git blob 108b691b0da5283c1fcede9d26b240f9bc5e9872
- [crates/proteus-core/src/core/execution_hooks.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/execution_hooks.rs) · Git blob 64da6c4b2814e05958cee35aad69c34be2c76ea4
- [crates/proteus-core/src/core/extension_operations.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/extension_operations.rs) · Git blob c42b32caab3309b9ff945e691cc5dd34647f53ef
- [docs/architecture/execution-runtime.md](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/docs/architecture/execution-runtime.md) · Git blob 0559b6150a5d1d67af9e8172bbae4a8f0789bc71
- [docs/architecture/hook-tool-operations.md](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/docs/architecture/hook-tool-operations.md) · Git blob e7024ded25bee6c678a5d530d02108cd5a110d6c
- [docs/guides/configuration.md](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/docs/guides/configuration.md) · Git blob 0a16b440f9c49a62f3598ae3cecd6b75966f445b
- [docs/guides/runtime-and-events.md](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/docs/guides/runtime-and-events.md) · Git blob 9bebaa1dec95d0d2c758a7ad502eaaadedb882e0
- [crates/proteus-core/src/core/model_call_scope.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/model_call_scope.rs) · Git blob aabbadc082eb118d593ed2f37de0ce8b26976bfc
- [crates/proteus-core/src/core/execution_hooks_tests.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/execution_hooks_tests.rs) · Git blob dd0c0921afea8cc1b7582da881cc649c5246b120
- [crates/proteus-core/src/core/bound_model/presentation.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_model/presentation.rs) · Git blob 50ccabb81a414ca1a058b4ab06cecddec2fbe26d
- [crates/proteus-core/src/core/runtime/execution_binding.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/runtime/execution_binding.rs) · Git blob ed19dfe8a1e75199f54f80cef629d3c78df9bc5f
- [crates/proteus-core/src/process_adapters/hook.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/process_adapters/hook.rs) · Git blob 46a58e52b6792c056d843fc10beb67597e71cdc1
- [crates/proteus-core/src/core/bound_model_tests.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/bound_model_tests.rs) · Git blob 27b3820c805b5e1d55d3356ea31c5a69d24bb04b
- [crates/proteus-core/src/core/extension_operations_tests.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/extension_operations_tests.rs) · Git blob 72a71aec2ad38a7ffd4e37a31c1b7d85ab5bb3f9
- [crates/proteus-contracts/src/contracts/execution.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-contracts/src/contracts/execution.rs) · Git blob 0d69c54b8f82fdbd0b9b3778d02e8d42f7992d36
- [crates/proteus-core/src/core/config.rs](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/crates/proteus-core/src/core/config.rs) · Git blob 7b923579b4f2da7eb70e46940b78ba4e1bb74e13
