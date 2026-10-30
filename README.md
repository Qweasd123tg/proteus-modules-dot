# Proteus Modules Dot

Исследования других агентов, независимые Rust-модули и небольшие patches для Proteus. Этот репозиторий — место разработки и передачи изменений, а не дистрибутив Core и не единый Cargo workspace.

## С чего начать

- **Новые механизмы и оптимизации:** [исследование архитектур агентов](research/agent-architectures-20261028/README.md). Здесь разделены подключаемые process modules, host-facing прототипы и patches для upstream.
- **Выбрать место для изменения:** [карта разработки](docs/DEVELOPMENT-MAP.md).
- **Готовые примеры контрактов:** [планировщик шагов](examples/pi-ready-steps/), [блоки контекста](examples/letta-evidence-blocks/), [verification hook](examples/hermes-verify-evidence/), [portable skills](examples/portable-skill-catalog/).
- **Сборка отдельных компонентов:** [Desktop](build-speed/desktop/), [Extensions](build-speed/extensions/). Применимость каждого patch определяется его собственной базовой ревизией.

- **Исторический runtime packet и поправка mode08:** [согласованность настроек, replay после reset и outbound accounting](foundation/2026-10-30/runtime-consistency/). База — Core `925de0f`; код уже перенесён upstream. Исправленный 08 заменяет неполный delivery artifact, а не предназначен для повторного применения к свежему Core.
- **Последующая историческая доставка:** [PR62](https://github.com/Qweasd123tg/proteus-modules-dot/pull/62) остаётся draft; все 6 изменений уже перенесены upstream. [Packet и отчёт о переносе на зафиксированном head](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a8f5315423c0d2a07c3236855f37a97a03d6f976/foundation/2026-10-30/validated-followups/README.md) не нужно применять повторно.
- **Новые независимые source-патчи:** [PR63](https://github.com/Qweasd123tg/proteus-modules-dot/pull/63), open draft: [владение terminal receipt](https://github.com/Qweasd123tg/proteus-modules-dot/blob/6ca100ed770aece472dd5f6139047489091240dc/foundation/2026-10-30/terminal-receipt-ownership/README.md) и [потоковая запись ZIP Extensions](https://github.com/Qweasd123tg/proteus-modules-dot/blob/6ca100ed770aece472dd5f6139047489091240dc/performance/2026-10-30/streaming-extension-archives/README.md). Их свежие базы и ограничения указаны в пакетах; успешные executable gates не заявлены.

- **Экспериментальный process hook:** [наблюдатель повторяющихся tool results](research/2026-10-30/loop-observer/). Opt-in исходники и regression sources, без заявления о выполненных runtime-проверках.

## Новые независимые предложения — 30 октября

- [PR65](https://github.com/Qweasd123tg/proteus-modules-dot/pull/65): [владение worktree](https://github.com/Qweasd123tg/proteus-modules-dot/blob/04deb8b11ec3b57348d6755a4307a83d5dbc8bb0/foundation/2026-10-30/worktree-ownership/README.md) и [один Responses client](https://github.com/Qweasd123tg/proteus-modules-dot/blob/04deb8b11ec3b57348d6755a4307a83d5dbc8bb0/performance/2026-10-30/single-responses-client/README.md).
- [PR66](https://github.com/Qweasd123tg/proteus-modules-dot/pull/66): [временный индекс строк tool](https://github.com/Qweasd123tg/proteus-modules-dot/blob/5de92063f4b86a8b606e906c709024aae4692163/performance/2026-10-30/render-local-tool-index/README.md) и [capture writer без polling](https://github.com/Qweasd123tg/proteus-modules-dot/blob/5de92063f4b86a8b606e906c709024aae4692163/performance/2026-10-30/capture-writer-notifications/README.md). Индекс добавляет временную память; снижение RAM не заявляется.
- [PR67](https://github.com/Qweasd123tg/proteus-modules-dot/pull/67): [координированные API proposals](https://github.com/Qweasd123tg/proteus-modules-dot/blob/afcdd86618a434003d49cc96755ded482c1cf8f2/research/2026-10-30/coordinated-api-proposals/README.md), включая typed workflow и contracts runtime feature. Это не drop-in интеграция: нужны настоящий Core commit, consumer pins/locks и executable gates.
- [PR68](https://github.com/Qweasd123tg/proteus-modules-dot/pull/68): [conformance CLI dependency boundary](https://github.com/Qweasd123tg/proteus-modules-dot/blob/29515aae1c214789a7402c4a82e989fa313610e7/build-speed/2026-10-30/protocol-conformance-cli/README.md). CLI tests остаются в полном runner; выбранный dependency graph требует проверки.

- [PR69](https://github.com/Qweasd123tg/proteus-modules-dot/pull/69): [ограниченные ready-порции live Desktop](https://github.com/Qweasd123tg/proteus-modules-dot/blob/06b3b2bc231b15ae81296071ecb215f64257a6f0/performance/2026-10-30/bounded-desktop-live-pump/README.md), 256 событий и явный yield. Общий backlog остаётся unbounded; frame/latency SLA не заявлен.
- [PR70](https://github.com/Qweasd123tg/proteus-modules-dot/pull/70): [согласование после reconnect/lag](https://github.com/Qweasd123tg/proteus-modules-dot/blob/0b835868058dd58a608a707fc1f3d6ba7c5bd9c8/foundation/2026-10-30/desktop-resync/README.md). Восстановление известного RunSettled и config refresh; использовать общий patch либо два standalone, не все три. Композиция с PR69 проверена в обоих порядках.

- [PR71](https://github.com/Qweasd123tg/proteus-modules-dot/pull/71): [self-drop broker](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a0b008554544db1b22b6e81fe525b27df080c836/foundation/2026-10-30/broker-final-owner/README.md) и [скрытые diff внутри compact-цепочки](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a0b008554544db1b22b6e81fe525b27df080c836/performance/2026-10-30/hidden-chain-diffs/README.md). [Дополнение о совместимости Core/Desktop](docs/source-composition-2026-10-30/pr71/README.md) не подменяет runtime/native gates.

- [PR72](https://github.com/Qweasd123tg/proteus-modules-dot/pull/72): [потеря пробуждения process writer при остановке](https://github.com/Qweasd123tg/proteus-modules-dot/blob/6a5d2e5b63e50d7cc035095a4ee791c4f5f0df01/foundation/2026-10-30/writer-stop-wake/README.md). Независимое узкое исправление, композиция с PR71 в обоих порядках проверена. Actual transport fixture только исходником; точная гонка не форсируется, executable gates остаются.

- [PR73](https://github.com/Qweasd123tg/proteus-modules-dot/pull/73): [общий payload событий app-server](https://github.com/Qweasd123tg/proteus-modules-dot/blob/6a57de168a3a4b2f8baaec929b0cf50d8da62941/research/2026-10-30/shared-event-ownership/README.md). Public Rust subscribe меняет return type на Arc; JSON/Contracts и owned AppSubscription остаются прежними. [Дополнение о композиции](docs/source-composition-2026-10-30/pr73/README.md).

Все перечисленные пакеты опубликованы как draft source proposals. Проверены исходники, применимость и описанные статические gates; успешные compile/tests/runtime/benchmarks не заявлены. Каждый пакет имеет свою базу и ограничения. Они не составляют одну обязательную цепочку применения.

[Совместное применение source-пакетов](docs/source-composition-2026-10-30/README.md): точные базы, независимые и optional API orders, проверенная композиция и незакрытые интеграционные gates. Статическая применимость не заменяет runtime-проверки.

## Как устроен репозиторий

| Каталог | Назначение |
|---|---|
| `examples/`, `hook/`, `consumers/` | Независимые примеры и адаптеры; контракт и команда сборки находятся рядом с кодом |
| `research/` | Исследования, проектные предложения и новые source-only компоненты |
| `build-speed/` | Изменения сборочных границ и запускателей по компонентам |
| `foundation/`, `ownership/`, `performance/` | Датированные patches и эксперименты с фундаментом runtime |
| `conformance/`, `integration/`, `experiments/` | Отдельные проверки конкретных контрактов и закреплённых составов |
| `validation/`, `benchmarks/`, `ci/` | Результаты, измерительные инструменты и вспомогательные проверяющие программы; не общий статус продукта |

## Работа с компонентом

1. Откройте README выбранного каталога: узнайте его тип, SDK/Core pin и зависимости.
2. Для самостоятельного crate используйте его собственный manifest/toolchain/lockfile. Не объединяйте независимые workspaces автоматически.
3. Для patch сначала проверьте указанную базовую ревизию и затронутые файлы. Наличие patch здесь не означает, что он уже применён в upstream.
4. Process module подключайте явно через его profile fragment. Host-facing библиотека требует адаптера в runtime; одной записи в конфиге недостаточно.
5. Проверяйте изменённый компонент и действительно затронутую интеграционную границу. Команды и результаты другого семейства не заменяют эту проверку.

`python3 scripts/check_examples.py` относится к первоначальным трём примерам, **не ко всему репозиторию**. Остальные команды находятся в README соответствующих каталогов. SDK pins разных примеров могут различаться намеренно.

Не регистрируйте одновременно Hermes v1 и strict Hermes v2 с одинаковым identity `hermes.verify_evidence`. Profile fragments не следует механически объединять.

## Статус и история

Сверка 30 октября 2026: [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60)
и [PR61](https://github.com/Qweasd123tg/proteus-modules-dot/pull/61) слиты в delivery;
[PR62](https://github.com/Qweasd123tg/proteus-modules-dot/pull/62) остаётся open draft,
хотя его изменения уже перенесены в upstream; [PR63](https://github.com/Qweasd123tg/proteus-modules-dot/pull/63)
содержит два новых независимых source-патча и также остаётся draft.
Это разные статусы, не повод повторять исторические patches.
Mode08 исправлен по пользовательскому Core `b062bb3` и уже
присутствует в `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Отдельный alpha API proposal packet опубликован в PR67; он не входит в PR62
или историческую runtime-серию. Новые PR65–73 остаются draft. Публикация артефакта
не завершает upstream интеграцию: реальные pins и исполняемые gates проверяются отдельно.

У этого репозитория нет одного глобального «все проверки прошли». Исторические результаты относятся к указанным в них commit, входам и сценариям. Новые исходники отдельно обозначают, что запускалось, а что ещё требует проверки.

[INTEGRATION-CANDIDATE.json](docs/INTEGRATION-CANDIDATE.json) и [DELIVERY-GUIDE.md](docs/DELIVERY-GUIDE.md) сохраняются как исторические снимки ранних поставок. Их ветки, состояния PR и состав CI не являются текущей картой проекта. [Предыдущий README](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a64384d6ae8a3810d87ece435f8554d75e7eedf8/README.md) содержит исходные инструкции и результаты первых примеров; они сохранены в Git, а не продублированы на главной странице.

Основные проекты: [Core](https://github.com/Proteus-harness/Proteus-core), [Modules](https://github.com/Proteus-harness/Proteus-modules), [Desktop](https://github.com/Proteus-harness/Proteus-desktop). Изменение этого репозитория само по себе не обновляет их.
