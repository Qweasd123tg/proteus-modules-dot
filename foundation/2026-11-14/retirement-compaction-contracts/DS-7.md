# DS7: cumulative compaction evidence сжимается до одного report при durable commit

## Статус

**Source-only integration finding: accepted plural report list теряет элементы на singular journal boundary.** Рекомендуемая квалификация: узкая корректность diagnostics/replay evidence (P3; более высокий приоритет только если batch-report workflow используется как regression gate). Не заявляется потеря итоговых сообщений, нарушение обычного cold resume или проявление в shipped/default workflow.

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87–89, tree `00a3c04a70d7927d1688ea155142025f596a2874`. Production исходники не менялись. Rust toolchain, runtime, HTTP, GUI, provider и проектные scripts/tests не запускались. Выполнена только собственная абстрактная Python-модель report-selection/counting, не production reproducer. Независимый source review подтвердил report-loss/cardinality; оговорки включены ниже.

## Контракт

- `proteus-contracts/src/contracts/workflow.rs:322–357`: `WorkflowOutput` имеет `compactions: Vec<HistoryCompactionReport>` и optional final replacement.
- `workflow_failure.rs:11–34`: cumulative progress имеет такой же vector.
- `workflow_checkpoint.rs:48–61`: checkpoint использует cumulative update относительно initial history; никакого cardinality `<=1 new changed report` здесь нет.
- `runtime/history/compacted_user.rs:10–12,18–50` явно обрабатывает цепочку reports; полный test `repeated_compactions_must_preserve_the_end_of_the_current_input_chain` принимает два последовательных changed reports.
- `runtime/tests.rs::CompactingWorkflow` прямо возвращает local replacement/report без ContextPreparation callback. Значит такой terminal update не следует объявлять автоматически невалидным только из-за отсутствия hook invocation.
- `docs/architecture/process-module-architecture.md:524–568` описывает plural cumulative compactions. Запрет возвращать unacknowledged **staged host preparation candidate** не используется в данном сценарии: никаких host preparation candidates не создаётся.
- `docs/architecture/canonical-turn-data.md:397–411` обещает сравнение changed compaction evidence на replay, в том числе отличий при равных final output/history.

## Причинная цепочка

### Основной минимальный сценарий: inactive hooks, без explicit checkpoints

1. Custom model-free workflow получает initial H, оканчивающуюся exact accepted user U. Он локально выполняет два compaction шага, preserving U, и возвращает replacement R, один assistant answer и два разных changed reports `[C1,C2]`. Для чистого примера `user_message_replacements=[]`, deterministic summaries/metadata, никаких tools/steering/concurrency.
2. При `hooks.is_active() == false` `reviewed_workflow.rs:51–54` напрямую возвращает Workflow result, **не** создавая automatic completion-review checkpoint.
3. `runtime/turn.rs:420–476` проверяет accepted preparations, нормализует output, вызывает `prepare_history_update`, затем `commit_history_update`.
4. `runtime/history.rs:94–111` проверяет compaction/replacement согласованность и final user preservation по всему vector. Наличие двух changed reports не отклоняется.
5. `commit_history_update` (`history.rs:130–155`) выбирает `changed.skip(recorded_compactions).last()`. При ещё не записанных reports это `C2`.
6. `history.rs:186–195` передаёт только `Some(C2)` в `replace_history`. `session_store/writer.rs:279–307` создаёт один `HistoryMutated`, у которого `compaction: Option<HistoryCompactionReport>` (`session_journal/types.rs:50–58`). `C1` нигде в этом пути не записывается. Итоговая history сохраняется как запрошено; report evidence не эквивалентен принятому vector.
7. `projection.rs:224–234` увеличивает `history_compactions` один раз на такой journal record. Cold replay `fixture.rs:430–455` восстанавливает list `[C2]`, а не `[C1,C2]`.
8. `normalize.rs::changed_compactions_equal` сравнивает полные lists changed reports. `workflow_replay/mod.rs:369–393` добавляет `workflow changed compaction reports differ from the canonical journal` при исходном unchanged workflow, возвращающем `[C1,C2]`.

Ни crash, ни I/O error, ни cancellation для потери C1 не нужны. Даже две одинаковые записи теряют cardinality; разные C1/C2 удобнее показывают потерю самостоятельного evidence.

### Связанный count mismatch, не отдельный finding

`runtime/checkpoint.rs:139–145` тоже выбирает только последний новый changed report, но затем `:182–189` принимает длину **всего** предложенного vector. Если один checkpoint принимает `[C1,C2]`, durable journal содержит C2 и count=1, а local recorder считает accepted changed=2. Terminal `commit_history_update` получает count=1 от journal и снова выбирает `skip(1).last() == C2`, даже когда final history совпадает с checkpoint. Через ветвь `history.rs:158–174` получается `[C2,C2]`, а не `[C1,C2]`.

Такой checkpoint может быть explicit; active completion-review hooks создают его автоматически для successful candidate (`reviewed_workflow.rs:83–100`). Это отдельная prerequisite, не основной no-hooks witness. При **одном** новом changed report на каждый checkpoint счётчики остаются согласованными.

## Важный replay caveat из review

Нельзя утверждать, что в no-callback сценарии единственным diagnostic будет vector mismatch или что один report даёт полный replay PASS. `ReplayState::summary` (`replay_runtime.rs:358–367`) отдельно требует `ExpectedCompaction.consumed`, а `preparation.rs:59–71` помечает его только при replay ContextPreparation. Прямой local compaction без callback может уже давать `workflow did not reproduce ... recorded changed compaction(s)`, даже при одном сохранённом report.

Это не отменяет source-deduced потери C1 и exact-vector mismatch, но не позволяет выдавать предложенный standalone replay за изолированный однофакторный runtime regression. В данной публикации дополнительный consumption assumption **не считается отдельным finding**. Собственная модель проверяет именно report list equality, не `WorkflowReplayReport.comparison.matched`.

## Предлагаемая верификация, не выполнена

Первичный regression должен проверять фактические durable records, без зависимости от replay diagnostic:

1. Расширить существующий runtime CompactingWorkflow fixture. Seed H с несколькими previous messages и exact current U. Явно сохранить `modules.hooks=[]` в recording и replay module snapshots; оставить hooks inactive; fixture не вызывает model/provider/context/tool/checkpoint.
2. Получить distinct `[C1,C2]` с `changed=true`, `user_message_replacements=[]`, и final R, сохраняющий U; вернуть assistant answer. Дождаться успешного run.
3. Cold-read journal через обычный validator. Сравнить ordered durable changed report list с accepted `[C1,C2]`; текущий source предсказывает `[C2]`. Отдельно подтвердить ожидаемую final history и Success, чтобы не спутать report loss с rejection.
4. Контроли: один changed report; unchanged + один changed; два successive checkpoints по одному новому report; один checkpoint с двумя новыми reports и тот же terminal output. Последний source-путь предсказывает duplicate `[C2,C2]`.
5. После согласования полного report-storage контракта отдельно пройти workflow replay. Сохранить все diagnostics; не маскировать unconsumed-preparation caveat. Не ослаблять strict final history/output/report comparison для получения искусственного зелёного результата.

Прочитаны полные `workflow_replay/tests/compaction.rs`, `workflow_replay/replay_runtime/checkpoint_tests.rs`, `workflow_replay/tests/model_free.rs`, `runtime/history/compacted_user.rs` и relevant runtime history/checkpoint code. Existing replay tests сохраняют один changed report, проверяют opaque metadata и deliberately changed report divergence. Test с цепочкой двух reports проверяет validation helper, не durable cardinality. Не утверждается отсутствие такого test во всём репозитории.

## DRY и направление исправления

Причина шире одной `.last()`: три разных «счётчика progress» означают разные сущности:

- local `recorded_compactions`: число всех предложенных reports;
- local `recorded_changed_compactions`: число changed reports;
- durable `history_compactions`: число journal mutations с одним changed report.

Они совпадают только при неявном предположении «не больше одного нового changed report на commit». Этот инвариант не проверяется на приёме.

Предпочтительный системный вариант: один typed accepted compaction batch/prefix с явной cardinality, общий для checkpoint и terminal reconciliation. Если vector действительно разрешён, хранить ordered batch целиком в атомарном history mutation и считать один и тот же accepted prefix при warm/cold reads и lost-ACK reconciliation. Изменение journal shape требует явного schema-version решения по правилам проекта. Не создавать фиктивные intermediate history snapshots: текущий output передаёт только final replacement.

Более узкая альтернатива: явно ограничить contract одним **новым** changed report на commit и отклонять batch до принятия. Это изменение semantics, а не молчаливое исправление; его надо согласовать со всеми workflows. Простое сравнение только последнего report в replay или объединение arbitrary metadata скрывает потерю evidence и нарушает уже существующие strict tests.

## Дедуп и ограничения

- PR91–94 и DS6 не повторяются. Здесь нет fingerprint cap, direct run drop, precommit visibility, mixed clear snapshot или retired read.
- Полностью прочитаны опубликованные `replay-integrity/REPORT.md` (inferred capabilities), `hooks-replay/REPORT.md` (generic literal ID remap), `round3-core/REPORT.md`, `workflow-continuation/REPORT.md`, `context-memory/REPORT.md`. Указанные причины отличаются.
- По PR84 DOCX выполнен targeted поиск compaction/reports/checkpoint. Прямого matching batch-cardinality finding не найдено. Не заявляется exhaustive дедуп всех 97 отчётов.
- Применимость: contract-valid custom workflow, который batch-ит changed reports. Наличие такой последовательности в shipped Modules/default profiles на этом проходе не установлено. Frequency, provider effects, GUI и runtime результат не измерялись.

## Артефакты

Не включённая в пакет собственная абстрактная модель selection/counting, 5 cases, включая три list-equality controls. Ни один `true` в ней не является полным Rust replay PASS. Авторские source SHA-256 сверены; production не менялся.

## Закреплённые source anchors

Пути `core/...` относительны `crates/proteus-core/src/`. Ключевые production-файлы не менялись delivery PR87–89.

- [core/runtime/history.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/history.rs#L130-L195)
- [core/session_journal/types.rs](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/session_journal/types.rs#L50-L58)
