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

Сверка 30 октября 2026, 15:32 UTC: [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60)
и [PR61](https://github.com/Qweasd123tg/proteus-modules-dot/pull/61) слиты в delivery;
[PR62](https://github.com/Qweasd123tg/proteus-modules-dot/pull/62) остаётся open draft,
хотя его изменения уже перенесены в upstream; [PR63](https://github.com/Qweasd123tg/proteus-modules-dot/pull/63)
содержит два новых независимых source-патча и также остаётся draft.
Это разные статусы, не повод повторять исторические patches.
Mode08 исправлен по пользовательскому Core `b062bb3` и уже
присутствует в `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.
Отдельный alpha API proposal packet ещё не опубликован; он не входит в PR62
или историческую runtime-серию. Реальные pins и исполняемые gates для таких
изменений проверяются отдельно.

У этого репозитория нет одного глобального «все проверки прошли». Исторические результаты относятся к указанным в них commit, входам и сценариям. Новые исходники отдельно обозначают, что запускалось, а что ещё требует проверки.

[INTEGRATION-CANDIDATE.json](docs/INTEGRATION-CANDIDATE.json) и [DELIVERY-GUIDE.md](docs/DELIVERY-GUIDE.md) сохраняются как исторические снимки ранних поставок. Их ветки, состояния PR и состав CI не являются текущей картой проекта. [Предыдущий README](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a64384d6ae8a3810d87ece435f8554d75e7eedf8/README.md) содержит исходные инструкции и результаты первых примеров; они сохранены в Git, а не продублированы на главной странице.

Основные проекты: [Core](https://github.com/Proteus-harness/Proteus-core), [Modules](https://github.com/Proteus-harness/Proteus-modules), [Desktop](https://github.com/Proteus-harness/Proteus-desktop). Изменение этого репозитория само по себе не обновляет их.
