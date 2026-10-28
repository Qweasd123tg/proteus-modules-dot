# Архитектуры агентов и модули для Proteus

Срез исходников на 28 октября 2026 года. Цель — заимствовать полезные алгоритмы и точки расширения, сохраняя authority, воспроизводимость и ограничения ресурсов Proteus. Это не предложение заменить существующий runtime чужим framework.

## Что написано

**[tool-schema-budget](modules/tool-schema-budget/README.md)** — отдельный opt-in Rust process module для `hook/v6`. Он дополняет существующий динамический selector бюджетом сериализованных ToolSpec, а не ещё одним ограничением количества инструментов.

- Считает компактный JSON без создания полного промежуточного буфера.
- Сохраняет порядок и содержимое оставшихся схем, обязательные инструменты и поверхности, которые нельзя безопасно вызвать через deferred discovery.
- По умолчанию сохраняет обязательную группу при переполнении и сообщает исключение; строгий отказ включается отдельно.
- Шаблон не меняет `plan` и `review`. Бюджет не включает добавляемые workflow meta-tools и не является точным token budget провайдера.

Исходники прошли чтение на совместимость с закреплённым SDK. Компиляция, запуск и измерения не выполнялись; пример предназначен для отдельной проверки и явного подключения.

## Исследования

| Источники | Полезные направления | Отчёт |
|---|---|---|
| Pi и OpenCode | Resource-keyed file mutations; settlement-aware leases; предварительная compaction с отложенным применением; tool discovery | [Pi / OpenCode](reports/pi-opencode.md) |
| Codex и Claude Agent SDK | Ограничение объёма tool-каталога; immutable descriptor reuse; session-owned speculative compaction; адаптер внешнего harness | [Codex / Claude](reports/codex-claude.md) |
| Hermes и OpenClaw | Immutable skill snapshots и lexical index; стабильный prompt prefix; restart budgets; data-only delegation; доверенные effect receipts | [Hermes / OpenClaw](reports/hermes-openclaw.md) |
| LangGraph и Microsoft Agent Framework | Неопределённый исход внешних действий; semantic resume manifest; атомарное резервирование нескольких ресурсов | [Durable workflows](reports/durable-workflows.md) |

В отчётах закреплены первичные источники и ревизии. Реализованные у донора механизмы отделены от наших проектных предложений. Архивный AutoGen и unreleased durable extension не выдаются за рекомендуемые production-зависимости.

## Следующие направления

1. **Версионированный skill-каталог.** Расширить существующий importer снимками metadata и ограниченным индексом. Cache не заменяет проверку доступа. Межпроцессный shared cache не возникает от одного `Arc`.
2. **Координация file mutations.** Ввести host-owned resource footprint и lease, который не освобождается раньше фактического окончания эффекта. Не включать parallel-флаг у write/edit без этого контракта.
3. **Resume manifest.** Отличать совместимость protocol/schema от совместимости workflow, состояния и выбранного artifact после рестарта.
4. **Speculative compaction.** Готовить кандидат заранее, применять только к подходящему prefix/epoch. Нужен workflow/session-owned lifetime; нельзя продолжать host callbacks после завершения hook invocation.
5. **Совокупный admission.** Резервировать provider/process/write ресурсы целиком, поверх существующего scheduler. Наблюдаемая quota не равна reservation.

## Что не нужно дублировать

В Proteus уже есть typed hooks, bounded data/control lanes с byte limits, process generations, cancellation, canonical journal/replay, snapshot epochs, role process permits и освобождение decoded history в idle. Бесконечные очереди или timeout, который лишь прекращает ожидание, не являются улучшением этих механизмов.

## Две сопутствующие правки исходников

В [runtime-fixes](runtime-fixes/README.md) лежат небольшие patches: наблюдение cancellation во время admission/restart и согласованная публикация выбранного module artifact с rollback и проверкой reuse metadata. Это исходники для отдельных upstream-копий, не автоматически применённые изменения.

## База Proteus

- Core: `125a9eb4088991513e9f61d899469be2076e266c`.
- Modules: `5fa8978684a37e8083c64f4d6cf0289e72450c6a`.
- Desktop: `e9ca11aab25f6d3a8d09b79c8c5266c1320af2b6`.
- Desktop Extensions: `6acf72bcba18d71f5b75b21dbcc5ea2f08c4f278`.

Нет утверждения о приросте TPS, снижении RAM или ускорении сборки: здесь исследование механизмов и новые исходники, без замеров. Нет изменений существующих runtime defaults, upstream repositories или CI workflows.
