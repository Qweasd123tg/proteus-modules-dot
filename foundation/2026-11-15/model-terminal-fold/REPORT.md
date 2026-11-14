# MDC-1: один canonical completion fold вместо трёх

## Итог

**Source-only исправление известного PR99/MDC-1**, не новая finding и не подтверждённый runtime fix. Исправляется потеря уже корректного typed ModelFailure в inherited public Rust `Model::complete`. Затем удаляются две дублирующие реализации этого fold у ModelService и BoundModel: они используют общий default, но продолжают строить собственные прежние streams.

Это устраняет источник расхождения, а не добавляет provider-specific обход. Нового публичного helper, trait, DTO или dependency нет. В трёх затронутых production prefixes число completion folds сокращается **3 → 1**, строки **726 → 701**. Методика и nonblank counts в `MEASUREMENTS.json`. Польза заключается в общей terminal semantics; latency/RAM/CPU не измерялись.

## Версии и дедуп

- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules main: `c035142558f0fca43e9772fc0e50ca293abf1531`, actual Core dependency pin `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery main на проверке: `2750e5511aadc5e293cbd60d53919fa29fcb6259`, включает PR110.
- [PR99/MDC-1](https://github.com/Qweasd123tg/proteus-modules-dot/pull/99) уже описал defect в direct Rust helper. Предыдущий source report доступен в PR99. Здесь новый fix candidate, а не повторная заявка finding.
- Contract `model.rs` actual Modules pin и Core main побайтно одинаков в baseline. Это подтверждает наличие той же ошибки, но **не обновляет** pinned dependency.

## Почему исправление фундаментальное

Default `complete` раньше распознавал только Response. Валидный canonical `Ok(Error { failure })` игнорировался, после чего normal EOF превращался в другую generic ошибку. Терялись kind, message, retry advice и completed_messages, хотя provider уже передал полный DTO.

Новый default имеет один явный fold:

- Response возвращается без реконструкции или изменения.
- Canonical Error немедленно возвращает исходный owned failure через anyhow::Error::new, сохраняя downcastable DTO.
- Outer stream/start Err по-прежнему проходит через `?`.
- Нетерминальные события не собираются в выдуманный ответ или failure progress.
- Настоящий EOF raw helper сохраняет прежний текст и прежнюю untyped error semantics.

ModelService и BoundModel раньше имели правильные, но отдельные копии этого fold. Удаление overrides предотвращает повторное расхождение между ними и default. Сам `complete` по-прежнему вызывает `self.stream(request)`, а не adapter.stream напрямую.

## Сохранность wrapper boundaries

**ModelService:** его неизменённый `stream` выполняет request shaping и возвращает validating_stream. Последний проверяет Response и сам выдаёт прежнюю EOF ошибку `model stream ended without Response event` до завершения iterator. Поэтому переход на default не заменяет observable EOF diagnostic другой строкой.

**BoundModel:** неизменённый `stream_with_deadline` всегда оборачивает provider stream в bound_recording_stream. Тот сохраняет deadline/cancellation, reconciles completed progress, записывает terminal outcome и сам выдаёт прежний typed EOF с progress. Auxiliary path возвращает этот recording stream прямо. Presentation path передаёт errors через `event?`, а canonical terminal через `yield event`. Новый default получает тот же подготовленный outcome.

Shaping, validation, journals, deadlines, presentation и progress ownership не перенесены в contracts и не обходятся. В patch нет изменений этих stream implementations. Проверено отдельно, что перенос CanonicalModelResponse import в bound_model_tests.rs сохраняет зависимость tests от прежнего `super::*`; неиспользуемый production import удалён.

Это source proof о текущих implementations, не выполненная wrapper regression suite. Если будущая wrapper stream начнёт завершаться голым None без собственных terminal/error checks, она попадёт в default EOF fallback. Candidate не вводит promise, что будущие произвольные implementations имеют сегодняшние wrapper guarantees.

## Точный scope

Исправляемая ошибка относится к inherited direct Rust Model API, raw process-backed adapter/custom stream-only implementation. Обычные ModelService/BoundModel calls уже правильно возвращали canonical failures. Не заявляются stock workflow outage, отказ automatic retries, потеря persisted history или новый пользовательский incident.

PR108/PR110 находятся в Modules; этот patch меняет Core. PR110 создаёт корректные provider-specific failure kinds, этот candidate сохраняет любые уже корректные canonical failures в generic helper. Их source edits не пересекаются, но совместная сборка или работа не проверены. Для Modules требуется отдельно осмысленно обновить Core dependency pin и пересобрать потребителей; здесь pin/lockfiles/production binaries не менялись.

## Предложенное покрытие, NOT RUN

Добавлен отдельный `contracts/model/tests.rs` с stream-only in-memory Model, который намеренно не переопределяет complete:

1. Полный canonical Error DTO для всех шести существующих kinds, включая Retryable advice и completed message. Completed event перед Error не дублирует authoritative failure progress.
2. Успешный Response после text delta сохраняется целиком, включая usage/identities.
3. Start failure и outer stream item Err остаются typed, включая anyhow context.
4. Empty/nonterminal-only EOF сохраняет прежний generic error.

Расширены два существующих wrapper tests: ModelService сравнивает весь failure DTO; BoundModel progress-merging scenario дополнительно проверяет typed Retryable advice и сообщение. Существующие EOF/deadline/validation controls не переписаны и должны быть запущены при доступном toolchain.

Тестовые зависимости уже есть в crate Cargo.toml. Новые тесты не запускались, Rust syntax/type-check/rustfmt не проверялись инструментом. Нет process launch, provider HTTP, cold history/replay или completed-message persistence run. Invalid Error→Response последовательности не используются как доказательство reachability.

## Выполненная проверка

- 15 точных baseline source blobs сверены с Git SHA; SHA256/размеры сохранены.
- Standalone patch прошёл `git apply --check --whitespace=error` и текстовое применение в отдельной копии; результат совпал с after bytes.
- Exact source review выполнен независимым reviewer; итог и пределы в `MODEL-TERMINAL-INDEPENDENT-REVIEW.md`.
- Не запускались Rust/cargo/compiler/rustfmt/clippy, project scripts, tests, fixtures, providers или приложение; toolchain/dependencies не устанавливались.
- Production checkouts, commits/refs, dependency pins и публикации не менялись.

Перед интеграцией нужны focused contracts/default tests, ModelService и BoundModel controls, затем применимый полный Core Rust gate и module-swap/consumer проверки по стандарту shared contracts. Пока этого нет, результат пригоден только как непроверенный source candidate.

## Артефакты

Публикуются patch, REPORT, независимый review, SOURCES.json, PATCH-VERIFICATION.json и MEASUREMENTS.json. Полные рабочие копии и логи не публикуются. Проверки относятся к подготовке candidate до публикации; merge пакета не применяет patch в upstream.
