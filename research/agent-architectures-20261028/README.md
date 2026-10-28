# Архитектуры агентов и модули для Proteus

Срез исходников на 28 октября 2026 года. Цель — заимствовать полезные алгоритмы и точки расширения, сохраняя authority, воспроизводимость и ограничения ресурсов Proteus. Это не предложение заменить существующий runtime чужим framework.

## Что написано

**[tool-schema-budget](modules/tool-schema-budget/README.md)** — отдельный opt-in Rust process module для `hook/v6`. Он дополняет существующий динамический selector бюджетом сериализованных ToolSpec, а не ещё одним ограничением количества инструментов.

- Считает компактный JSON без создания полного промежуточного буфера.
- Сохраняет порядок и содержимое оставшихся схем, обязательные инструменты и поверхности, которые нельзя безопасно вызвать через deferred discovery.
- По умолчанию сохраняет обязательную группу при переполнении и сообщает исключение; строгий отказ включается отдельно.
- Шаблон не меняет `plan` и `review`. Бюджет не включает добавляемые workflow meta-tools и не является точным token budget провайдера.

Также написаны семь независимых Rust-библиотек для экспериментов с архитектурой host:

| Прототип | Что реализует | Чего пока нет |
|---|---|---|
| [Resume manifest](modules/resume-manifest-prototype/README.md) | Каноническая identity и сравнение engine/workflow/state/artifact для холодного продолжения | Подключения к Core, миграции и автоматического resume |
| [Resource admission](modules/resource-admission-policy/README.md) | Ограниченная очередь, FIFO/aging и цельный план распределения нескольких ресурсов | Резервирования реальных permits и исполнения этого плана |
| [Mutation lease](modules/mutation-lease-state-machine-prototype/README.md) | Host-owned lease, который переживает отмену requester; barrier при неизвестном исходе | Общего workspace owner/IPC и подтверждения физического settlement |
| [Skill index](modules/skill-index/README.md) | Ограниченный lexical search по metadata/разрешённым body prefixes с актуальным candidate scope | tool/v6 adapter; индекс не заменяет свежую загрузку skill |
| [Compaction candidate owner](modules/compaction-candidate/README.md) | Владение предварительно подготовленным контекстом, prefix/epoch CAS, отмена и uncertain-commit fence | Модельных задач, настоящего Core transaction и durable checkpoint |
| [Output capture](modules/output-capture/README.md) | Streaming artifact tap до RPC, cap и отдельные статусы capture/команды | Файлового sink, общих квот и async reader adapter |
| [Context segments](modules/context-segments/README.md) | Допустимые границы сокращения истории с целыми tool pairs/batches/provider groups | Адаптера canonical history и применения compaction |

Это заменяемые policy/state-machine библиотеки, не новые самостоятельно разрешающие действия runtime. При интеграции остаётся один владелец authority и ресурсов.

Исходники просмотрены на согласованность с описанными контрактами. Компиляция, запуск и измерения не выполнялись; примеры предназначены для отдельной проверки и явного подключения.

## Исследования

| Источники | Полезные направления | Отчёт |
|---|---|---|
| Pi и OpenCode | Resource-keyed file mutations; settlement-aware leases; предварительная compaction с отложенным применением; tool discovery | [Pi / OpenCode](reports/pi-opencode.md) |
| Codex и Claude Agent SDK | Ограничение объёма tool-каталога; immutable descriptor reuse; session-owned speculative compaction; адаптер внешнего harness | [Codex / Claude](reports/codex-claude.md) |
| Hermes и OpenClaw | Immutable skill snapshots и lexical index; стабильный prompt prefix; restart budgets; data-only delegation; доверенные effect receipts | [Hermes / OpenClaw](reports/hermes-openclaw.md) |
| LangGraph и Microsoft Agent Framework | Неопределённый исход внешних действий; semantic resume manifest; атомарное резервирование нескольких ресурсов | [Durable workflows](reports/durable-workflows.md) |
| OpenHands SDK и Deep Agents | Безопасные границы сокращения истории; capture-at-source; skill-anchored tool visibility; границы subagent handoff | [OpenHands / Deep Agents](reports/openhands-deepagents.md) |
| Goose и PydanticAI | Семантическое сокращение схем, loop observer и диагностика provider cache | [Goose / PydanticAI](reports/goose-pydanticai.md) |

В отчётах закреплены первичные источники и ревизии. Реализованные у донора механизмы отделены от наших проектных предложений. Архивный AutoGen и unreleased durable extension не выдаются за рекомендуемые production-зависимости.

## Следующие направления

1. **Версионированный skill-каталог.** Первый patch со snapshot/cache уже написан для существующего importer. Теперь готов и bounded lexical index; ближайшее подключение — отдельный opt-in search tool поверх fresh discovery. Cache не заменяет проверку доступа. Межпроцессный shared cache не возникает от одного `Arc`.
2. **Координация file mutations.** State-machine прототип готов; следующий шаг — настоящий host-owned resource footprint и settlement adapter. Не включать parallel-флаг у write/edit до этой интеграции.
3. **Resume manifest.** Диагностическая библиотека готова. Интеграция должна различать совместимость protocol/schema и workflow/state/artifact после рестарта, а не автоматически разрешать продолжение.
4. **Speculative compaction.** Candidate owner уже реализован как библиотека. Следующий шаг — adapter настоящего session transaction и bounded worker snapshot; нельзя продолжать host callbacks после завершения hook invocation.
5. **Совокупный admission.** Policy-прототип готов. Host должен резервировать provider/process/write ресурсы целиком поверх существующего scheduler; наблюдаемая quota не равна reservation.

## Что не нужно дублировать

В Proteus уже есть typed hooks, bounded data/control lanes с byte limits, process generations, cancellation, canonical journal/replay, snapshot epochs, role process permits и освобождение decoded history в idle. Бесконечные очереди или timeout, который лишь прекращает ожидание, не являются улучшением этих механизмов.

## Сопутствующие правки исходников

В [runtime-fixes](runtime-fixes/README.md) лежат patches: cancellation во время admission/restart; публикация выбранного artifact с rollback и проверкой reuse metadata; snapshots существующего skill-каталога; устранение повторного разбора terminal SSE JSON. Дополнительно [четыре copy-reduction patches](runtime-fixes/model-copy-reductions/README.md) убирают глубокую копию stream request, повторную копию TextDelta, копирование instructions перед сортировкой и FileRef перед форматированием. Это исходники для отдельных копий, не автоматически применённые изменения.

## База Proteus

- Core: `125a9eb4088991513e9f61d899469be2076e266c`.
- Modules: `5fa8978684a37e8083c64f4d6cf0289e72450c6a`.
- Desktop: `e9ca11aab25f6d3a8d09b79c8c5266c1320af2b6`.
- Desktop Extensions: `6acf72bcba18d71f5b75b21dbcc5ea2f08c4f278`.

Дополнительный проход model-copy-reductions и документации использует свежие Core `bd4aae62c738befcdf9b3a1a831837447ecb7aad` и Modules `ea459a60d8fce621ccabff33ff7ff9dc9d55573a`. Базы старых patches не переписываются задним числом.

Нет утверждения о приросте TPS, снижении RAM или ускорении сборки: здесь исследование механизмов и новые исходники, без замеров. Нет изменений существующих runtime defaults, upstream repositories или CI workflows.
