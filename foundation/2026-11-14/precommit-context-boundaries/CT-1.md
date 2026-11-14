# CT-1: doctor называет нулевой context deadline отключённым

**P3, source-only diagnostic/runtime mismatch.** `runtime.context_timeout_ms = 0` получает положительную диагностику `disabled`, но BoundContext создаёт timeout с нулевой длительностью. Доказан конфликт диагностического текста с runtime, а не обязательство реализовать unlimited context build.

## База и evidence

Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87 → PR88 → PR89, результирующее дерево `00a3c04a70d7927d1688ea155142025f596a2874`. Затронутые production-файлы этими delivery patches не изменены. Ссылки ниже закреплены на upstream commit; более поздний upstream не покрыт выводом.

Выполнены source trace, поиск validators/normalizers, проверка pinned Tokio implementation, дедупликация и независимая повторная проверка. Rust toolchain отсутствовал; tests/build, CLI/worker и runtime reproduction **не запускались**. Production не менялся.

## Цепочка

1. [`RuntimeConfig`:483–490](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config.rs#L483-L490) хранит `context_timeout_ms` как `u64`. [`load_path`:73–83](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/config/loading.rs#L73-L83) не запрещает zero. Поиск production references не обнаружил отдельного запрета или нормализации этого значения.
2. [`check_runtime_limits`:396–400](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_doctor.rs#L396-L400) передаёт context timeout в общий helper. [`check_timeout_ms`:420–421](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/cli_doctor.rs#L414-L429) при zero выдаёт `OK` с текстом `runtime.context_timeout_ms: disabled`.
3. [`RuntimeRegistry::bind_context`:46–53](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/registry.rs#L46-L53) передаёт исходное значение в BoundContext.
4. [`BoundContext::build`:64–74](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/bound_context.rs#L64-L74) без zero branch выполняет `tokio::time::timeout(Duration::from_millis(self.timeout_ms), self.inner.build(input))`. Значение zero не отключает local deadline; соответствующий error содержит `context build timed out after 0ms`.

## Ограничения вывода

- Это **не** утверждение, что любой context call с zero гарантированно падает. Закреплённый [Tokio 1.52.2](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/Cargo.lock#L2094-L2097) сначала [poll-ит inner future](https://github.com/tokio-rs/tokio/blob/tokio-1.52.2/tokio/src/time/timeout.rs#L205-L222), затем deadline. Немедленно готовый future может завершиться успешно; асинхронное ожидание не получает семантику отключённого timer.
- Документ [runtime-and-events:2276–2277 базового commit](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/runtime-and-events.md#L2276-L2277) обещает zero-disabled для **model и workflow**, не для context. В восстановленном результирующем дереве это строки 2280–2281. Поэтому нельзя объявить выбор zero-disabled для context уже принятым продуктовым контрактом.
- Даже если в будущем zero отключит local context timer, [`ProcessContextBuilder`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/context.rs#L31-L50) сохраняет отдельный finite protocol default 30 s без explicit export override. Unlimited process execution отсюда не следует.
- Типичность конфигурации zero, пользовательский инцидент, повреждение journal и потеря данных не установлены.

## Regression plan, НЕ РЕАЛИЗОВАН И НЕ ЗАПУЩЕН

1. Разобрать минимальный допустимый config с `context_timeout_ms = 0`; проверить фактическое сообщение doctor helper отдельно от запуска каких-либо modules.
2. Через RuntimeRegistry binding использовать test-owned ContextBuilder, который сигналит о начале, затем ждёт управляемый barrier. При zero сопоставить фактический outcome с заявлением `disabled`. Не использовать реальную сеть или длительный worker для изоляции local timer.
3. Controls: немедленно готовый ContextBuilder; положительный timeout с завершением до deadline; cancellation во время ожидания. Использовать управляемое тестовое время/barrier, а не случайную задержку.
4. После выбранного contract decision закрепить единый ожидаемый результат doctor и runtime. Process timeout проверять отдельно, чтобы local и wire budgets не смешались.

## Уточнение и упрощение, не выбранное исправление

Сначала выбрать семантику context zero. Если это zero-duration deadline, исправить диагностический текст или валидацию недопустимого значения. Если это отключение local timeout, реализовать это явно и согласовать диагностику/документацию. Обе ветки сохраняют независимые process limits.

Общий helper сейчас предполагает одинаковую семантику sentinel для разных полей. Упрощение заключается в одном явном определении семантики каждого deadline и использовании этого определения в runtime и диагностике, а не в механическом распространении `disabled` на все `u64` timeouts. Новый framework или публичный slot не требуется. LOC/latency/RSS не измерены.

## Review и дедупликация

Независимая source review подтвердила отсутствие zero validator/normalizer, прямой registry binding и unconditional local timeout. Отдельно потребовала сохранить ready-future exception, отсутствие документированного zero-disabled context promise и независимый process budget.

Проверены 97 материалов [continuous audit index](https://github.com/Qweasd123tg/proteus-modules-dot/blob/main/research/proteus-continuous-audit-2026-11-13/README.md), полный ноябрьский audit DOCX и содержание [PR91](https://github.com/Qweasd123tg/proteus-modules-dot/pull/91)/[PR92](https://github.com/Qweasd123tg/proteus-modules-dot/pull/92). Прямого дубликата в проверенном корпусе не найдено; абсолютная новизна не гарантируется. TC-2 из PR91 касается `ToolSpec` и process budget 1000 ms, а здесь найдено другое поле, общая context boundary и неверная диагностика. Общее семейство sentinel mismatch не следует выдавать за две независимые архитектурные причины.
