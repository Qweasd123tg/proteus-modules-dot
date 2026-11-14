# Core: продолжение функционального аудита

Дата: 2026-11-12. Проверяемый репозиторий: https://github.com/Proteus-harness/Proteus-core

HEAD/main: `89997df995df7c39b713e16aba216ecb19c8f497`. Remote SHA повторно проверен в конце прохода, не изменился. Изолированная рабочая копия: `/workspace/shared/core-functionality-round3`. Производственный код не изменён; добавлен только локальный воспроизводящий тест. Публикаций/PR нет.

## Новое подтверждение: ошибка уведомления превращает принятый steering-запрос в ошибочно отклонённый

Приоритет: P2 (корректность при отказе event sink, риск повторного исполнения работы).

`SessionSteering::reserve_message_now` сначала помещает сообщение в очередь и публикует её snapshot. После этого `AgentRuntime::bind_user_message_reservation` ждёт `SteeringQueued` и распространяет ошибку sink через `?`. В результате вызывающий получает `Err` вместо receipt, хотя сообщение уже принято. Повтор той же команды добавляет новый UUID и второй экземпляр работы. Эта очередь не удаляется при ошибке ack и действительно исполняется как follow-up.

Код:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/admission.rs#L99-L124
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/steering.rs#L208-L222
- Стандартный JsonlEventStore действительно может вернуть ошибку открытия/записи: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/event_store.rs#L31-L52

Изолированный repro использует настоящие AgentRuntime, очередь и follow-up workflow; заменён только EventSink, который возвращает ошибку на SteeringQueued и пропускает остальные события. Без реальных моделей, аккаунтов, сети и сторонних инструментальных эффектов.

Наблюдение:
```
attempt 1: Err; admitted=["same client request"]
attempt 2: Err; admitted=["same client request", "same client request"]
executed tasks after caller received two errors:
["initial", "same client request", "same client request"]
```

Тест `repro_failed_steering_ack_does_not_admit_retry_twice` падает именно на проверке фактически выполненных tasks. Три повторных запуска дают тот же результат. Это новое наблюдение, не прежняя гонка cancel/TurnSettled или ComponentLost.

Рекомендация: определить единственную точку принятия Send. После необратимого помещения в очередь нельзя сообщать просто «не принято» из-за вторичного runtime event. Либо успешный receipt с отдельной диагностикой event sink, либо транзакционная публикация до видимого принятия. Простой rollback после await небезопасен: consumer уже может забрать сообщение. Аналогичный шаблон mutate → emit? есть у edit/delete очереди, но отдельным воспроизведением они здесь не подтверждались.

## Проверки

Существующие целевые тесты: **51 passed, 0 failed**:
- steering integration, включая completion review: 6;
- steering queue/edit/weave: 6;
- bound model, сроки и терминальные события: 28;
- workflow host selection: 3;
- model context: 2;
- execution hooks: 4;
- canonical eval report: 2.

Отдельный repro: expected failure, повторён ещё 3 раза. `git diff --check` чистый.

Команда воспроизведения после применения только тестового patch к указанному SHA:
```
export PROTEUS_TEST_REFERENCE_MODULE=/path/to/proteus-reference-module
cargo test --locked -p proteus-core --lib repro_failed_steering_ack_does_not_admit_retry_twice -- --nocapture
```
Fixture была готовой официальной reference-module сборкой из предыдущего прохода. Первые два подготовительных запуска не считаются подтверждением: отсутствовала переменная fixture; затем тест был уточнён, чтобы заменить workflow до снимка admission. В окончательном логе проверяется реальное исполнение.

## Охват и ограничения

`coverage.tsv` перечисляет ровно прочитанные файлы/диапазоны. 40 файлов прочитаны целиком, 8203 строки, плюс выбранные диапазоны runtime/steering, admission plumbing и journal validation. Основной новый охват: workflow host/streams, completion review, before/after hooks, model/context bookkeeping, agent mailbox/pending work, prompt replay, steering mutation/admission/follow-up, execution snapshot/settings. Это **не** утверждение о чтении всего репозитория.

Не подтверждены и не включены как баги:
- подозрение на разный tool failure status в ToolEffect/ToolResult: canonical projection запрещает менять status/error/content, поэтому соответствующий сценарий невалиден;
- время BeforeModel hook вне провайдерского таймера: граница контракта требует отдельного уточнения, дефектом не объявлено.

Не выполнялись: полный workspace gate, HTTP/браузерный E2E, платные live-модели, Windows/macOS. Предыдущие runtime/storage находки повторно не воспроизводились. Изменения вне этой задачи не делались.

Артефакты: `repro-steering.patch`, `repro-steering.log`, `repro-repeat-{1,2,3}.log`, семь непустых логов штатных тестов, `coverage.tsv`. Файл `core_bound_model_tests.log` относится к первоначальному несовпавшему фильтру (0 тестов); реальные 28 находятся в `core_bound_model_tests_actual.log` и учитываются только один раз.
