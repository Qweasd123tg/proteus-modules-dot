# Proteus Modules Dot

Исследования других агентов, независимые Rust-модули и небольшие patches для Proteus. Этот репозиторий — место разработки и передачи изменений, а не дистрибутив Core и не единый Cargo workspace.

## С чего начать

- **Новые механизмы и оптимизации:** [исследование архитектур агентов](research/agent-architectures-20261028/README.md). Здесь разделены подключаемые process modules, host-facing прототипы и patches для upstream.
- **Выбрать место для изменения:** [карта разработки](docs/DEVELOPMENT-MAP.md).
- **Готовые примеры контрактов:** [планировщик шагов](examples/pi-ready-steps/), [блоки контекста](examples/letta-evidence-blocks/), [verification hook](examples/hermes-verify-evidence/), [portable skills](examples/portable-skill-catalog/).
- **Сборка отдельных компонентов:** [Desktop](build-speed/desktop/), [Extensions](build-speed/extensions/). Применимость каждого patch определяется его собственной базовой ревизией.

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

У этого репозитория нет одного глобального «все проверки прошли». Исторические результаты относятся к указанным в них commit, входам и сценариям. Новые исходники отдельно обозначают, что запускалось, а что ещё требует проверки.

[INTEGRATION-CANDIDATE.json](docs/INTEGRATION-CANDIDATE.json) и [DELIVERY-GUIDE.md](docs/DELIVERY-GUIDE.md) сохраняются как исторические снимки ранних поставок. Их ветки, состояния PR и состав CI не являются текущей картой проекта. [Предыдущий README](https://github.com/Qweasd123tg/proteus-modules-dot/blob/a64384d6ae8a3810d87ece435f8554d75e7eedf8/README.md) содержит исходные инструкции и результаты первых примеров; они сохранены в Git, а не продублированы на главной странице.

Основные проекты: [Core](https://github.com/Proteus-harness/Proteus-core), [Modules](https://github.com/Proteus-harness/Proteus-modules), [Desktop](https://github.com/Proteus-harness/Proteus-desktop). Изменение этого репозитория само по себе не обновляет их.
