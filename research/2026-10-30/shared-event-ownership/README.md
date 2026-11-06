# Общий immutable payload app-server — source-only предложение

База: `Proteus-harness/Proteus-core@befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Пакет содержит предложение для review, не проверенную сборку и не готовый runtime rollout.

## Изменение

Raw и sequenced broadcast используют один `Arc<AppServerEvent>` на публикацию.
View/pending обновляются до упаковки; сохраняется порядок sequenced → raw →
pending watch, прежние ёмкости, lag, snapshot retry и sequence filtering.
Нового cache, compatibility receiver, lock, queue policy или settings нет.

**Rust API намеренно несовместим:** `AppServerHandle::subscribe` теперь возвращает
`broadcast::Receiver<Arc<AppServerEvent>>`. Все найденные tracked callers и
test helpers мигрированы. Внешние Rust callers исчерпывающе не устанавливаются.
`AppSubscription::recv` возвращает прежний owned `AppServerEvent`, отфильтровав
покрытые события до `Arc::unwrap_or_clone`. Уникальность не гарантируется:
accepted delivery может клонировать payload. HTTP watcher только заимствует;
ACP копирует Runtime envelope для owned projection и approval ID для responder.

Contracts DTO, `StdioOutput::Event { event: Box<_> }`, JSON wire и client pins
не меняются. Отдельный HTTP activity channel остаётся owned. SSE queue и
unsupported action-route решения не затронуты.

## Границы результата

Структурно устранены отдельный deep clone между rings и ignored payload copies
у borrow-only потребителей. Это не измерение производительности или RSS.
Arc добавляет allocation/refcount; retained consumer может продлить жизнь payload
после вытеснения из ring. Reconnect snapshot по-прежнему создаёт owned DTO;
принятые SSE/stdio события и serialization остаются отдельной работой.

## Проверки

- 589/589 active Rust файлов pinned дерева проверены по Git blob SHA-1 и
  просмотрены поиском callers; 5 research файлов проверены только по hash.
- Независимый static review production, caller migration и пяти regression tests.
- Прямой установленный rustfmt: edition 2024, skip_children=true.
- Whitespace check; strict `git apply --check`, forward apply и побайтовое
  сравнение с candidate; reverse check/apply и сравнение с baseline — успешно.
- Regression sources: Arc identity обоих publications, error ownership без raw
  receiver/без receivers, raw lag/lifetime, owned independence и covered Shutdown.

**Не запускались:** проектный код, scripts, Cargo, tests, build, CI, benchmarks.
Тестовые исходники не являются evidence прохождения тестов. До adoption нужны
разрешённые compile/test gates по затронутой app-server/ACP/HTTP границе.

`source-identities.tsv` фиксирует pinned source coverage, `CALLERS.md` — callers,
`REVIEW.md` — независимый source-only review, `SHA256SUMS` — целостность пакета.
