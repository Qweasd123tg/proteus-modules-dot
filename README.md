# Единый integration candidate — исходники и независимые package gates

Эта экспериментальная ветка собирает точные принятые поставки PR #1–19 и отдельную проверенную совместимость portable skills с Core `1fc3ef223d10322815dd9290a50d045bc95402bb`. Это **сосуществование кода в одном checkout**, а не общий runtime, автоматическое включение модулей, production release или гарантия всего Core. Основная ветка и исходные draft PR не изменены.

## С чего начать

- [Карта точного состава и происхождения](docs/INTEGRATION-CANDIDATE.json): исходные PR/head/tree, Git blob каждого файла, разрешённое README-only объединение и новая CI-обёртка.
- [Исторический delivery guide](docs/DELIVERY-GUIDE.md) — снимок на 26 октября 2026, 09:26 UTC, **не текущее состояние этой объединённой ветки**. Его pending-статусы и ссылки относятся к исходным поставкам.
- [Исследования экосистем](research/ecosystems/), [операторские материалы](research/operator/) и [исторические evidence supplements](research/supplements/) не становятся новыми runtime-доказательствами от включения в checkout.

| Семейство | Читать / проверять отдельно |
|---|---|
| Pi, Letta, Hermes v1 | [Исходные три примера](#proteus-modules-dot); [21 scoped Core smoke](integration/core-smoke/) |
| Portable skills | [Модуль](examples/portable-skill-catalog/), [Core 3f pair](conformance/core-skills/), [отдельный Core 1fc + неизменённый модуль SDK 3f](conformance/current-core-skills/) |
| Строгие JSON receipts / Hermes v2 | [Самостоятельная strict pair](experiments/strict-pair/), [pinned full-turn fixture](integration/strict-host/) |
| Exact-byte evidence и CAS corrections | [Evidence spans](examples/evidence-spans/), [correction memory](examples/correction-memory/) |
| Supplied usage snapshots | [Usage attribution](consumers/usage-attribution/) — не transport, provider или billing |
| Hook adapters / opt-in argument guard | [Claude hooks](hook/claude-command-hooks/), [JavaScript guard](examples/js-argument-replacement-guard/) |
| Отдельные conformance probes | [rmcp](conformance/rmcp-lifecycle/), [native read cache](conformance/native-read-cache/), [append groups](conformance/append-groups/), [parser observations](conformance/parser-compat/) |

**Включение только opt-in.** Не объединяйте profile fragments автоматически. Hermes v1 и strict Hermes v2 экспортируют один hook identity `hermes.verify_evidence`: их нельзя зарегистрировать одновременно в одной сборке профиля. Отдельные workspace/lockfiles и SDK/Core pins сохранены; различающиеся зависимости намеренно не сведены в общий workspace. Используйте только выбранное семейство и его документированные входы/права.

## Что проверяет aggregate CI

Ожидаются **15 независимых package jobs в 13 push workflow runs**: 12 исходных workflow с подходящими path filters и новая candidate-only обёртка для трёх gates, чьи исходные push filters ограничены их собственными ветками (usage, strict full-turn, CAS). Обёртка сохраняет команды, права, лимиты и отдельные hosted runners; добавляет только собственную hash-привязку в входы supervisor. Исходные workflow и их frozen manifests неизменны.

Это повтор существующих package gates на одном точном head, **не тест одновременной активации всех модулей**. Нет новых runtime-тестов для docs-only исследований или отдельного JS guard сверх уже существующих workflows; их исходные результаты и ограничения остаются отдельными. Отсутствие workflow run, skipped или pending — не PASS. Итоговую фактическую матрицу run/job/artifact identities смотрите в draft PR и [Actions](https://github.com/Qweasd123tg/proteus-modules-dot/actions); этот файл сам по себе не удостоверяет будущие head.

После открытия draft PR исходные 15 workflows могут повториться на GitHub test-merge checkout; это отдельное доказательство, не удвоение числа тестов и не замена push-head evidence. Merge, auto-merge, ready conversion и deploy не выполняются.

## Сохранённые исходные инструкции

Ниже побайтно сохранены исходный README PR #1 и два непересекающихся добавления PR #3/#5. Их исторические формулировки описывают тогдашние проверки, а не всю последующую объединённую поставку. Точные оригинальные blobs и это явное README-only разрешение коллизии указаны в manifest.

---

# Proteus Modules Dot

Исследования агентных систем и небольшие исполняемые примеры модулей для Proteus. Цель — расширяемость без скрытого ослабления прав, журнала, отмены и жизненного цикла ресурсов.

## Три разных границы расширения

| Пример | Контракт | Что действительно делает | Чего не обещает |
|---|---|---|---|
| [Планировщик готовых шагов](examples/pi-ready-steps/) | tool/v6 | Проверяет ограниченный DAG и рекомендует готовые шаги | Не запускает задачи, не сохраняет workflow, не удостоверяет переданные статусы |
| [Блоки контекста](examples/letta-evidence-blocks/) | context_provider/v4 | Отбирает полные блоки с версиями, tombstone, scope и byte budget | Не подключается к Letta, не является долговременной памятью или ACL |
| [Свидетельство проверки перед завершением](examples/hermes-verify-evidence/) | hook/v6 | Ищет причинно более поздний результат настроенного verifier после мутации | Не выполняет тесты и не доказывает корректность; реальный receipt-emitting verifier подключается отдельно |

Это новые реализации, вдохновлённые Pi, Letta и Hermes, а не обещание совместимости с их плагинами или runtime. Исходные идеи и точные ограничения описаны внутри каждого примера. Core и основные модули Proteus не изменяются.

## Сборка и проверка

Требуются Python 3.11+, установленный Rust 1.95.0 с rustfmt, сетевой доступ для первоначальной загрузки закреплённых зависимостей. Все примеры — независимые Cargo workspaces с lockfile. SDK закреплён на [Proteus Core 3f36a003](https://github.com/Proteus-harness/Proteus-core/tree/3f36a003b4f3fde2242fc80f7aedac00dd127d1d).

```sh
python3 scripts/check_examples.py
```

Runner не устанавливает инструменты, не очищает caches, не запускает suites чужих проектов и не скрывает пропущенную проверку под успешным статусом. Он проверяет manifest/lock, форматирование, unit/policy tests, сборку и реальный процессный wire-интерфейс. Первый полный локальный прогон: 50 Rust tests PASS, 12 Python runner tests PASS, 14 дополнительных Pi wire checks PASS; без пропусков. Подробности: [VALIDATION.md](VALIDATION.md), результаты: [validation/results.json](validation/results.json).

Профили внутри примеров содержат явно отмеченные абсолютные пути-заглушки. Подставьте локальные executable paths. Полный запуск Core с этими профилями, живые модели, реальный verifier и производственные сценарии не входят в заявленный результат unit/wire проверок.

## Исследование

- [Обзор и приоритеты](research/overview.md).
- [Подробный каталог находок](research/catalog.json): маленькие и большие проблемы, оптимизации, полезные механизмы, осознанные ограничения и отклонённые гипотезы. Запись в каталоге не обязательно является багом.
- Статическое доказательство пути в исходнике, условный сценарий и динамическое воспроизведение различаются. Измеренное ускорение не заявляется без benchmark.
- Это широкий первый проход, не заявление, что изучен весь код всех существующих агентов.

Права, признание эффектов и результаты проверок нельзя делегировать свободному тексту модели или недоверенной metadata. При этом выбор алгоритмов, моделей, памяти и композиции может оставаться расширяемым. Подробные непроверенные security-сценарии не публикуются в этом общем каталоге.

Основные проекты: [Proteus Core](https://github.com/Proteus-harness/Proteus-core), [Proteus Modules](https://github.com/Proteus-harness/Proteus-modules).

## Проверка реальных границ Core

[Отдельный scoped smoke](integration/core-smoke/) линкует неизменённый Core/SDK 3f36a003 и проверяет 21 сценарий: загрузку профилей и static assembly, фактический BoundTools/policy/tool путь, hook chain и context-provider callbacks. [Локальный результат](validation/core-host-smoke-local/evidence.json) прошёл; это не полный agent turn, не запуск reference pack, не model/journal/replay или OS sandbox проверка. Для smoke добавлен отдельный CI workflow.

## Переносимый каталог skills

[portable-skill-catalog](examples/portable-skill-catalog/) добавляет context provider и read-only refresh/load tools: явно указанные корни, ранние лимиты, изоляция ошибок и проверка пути/хеша перед загрузкой. Hooks/scripts не запускаются, allowed-tools не выдаёт прав. Локально пройдены 29 behavior + 1 executable-wire test; настоящая Core-интеграция этого нового модуля пока не заявляется. Для него предусмотрен отдельный CI; общий runner выше относится только к первоначальным трём примерам. Прочитайте ограничение поддержки YAML parser в README модуля перед применением.
