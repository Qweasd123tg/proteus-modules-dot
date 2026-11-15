# Статус: все шесть изменений уже перенесены upstream

На Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc` и Modules
`200d1ec54f1217f61a31823db939df3799c638dc` повторное применение не требуется.
[Сверка всех файлов и пользовательских дополнений](ported-2026-10-30/PORTED.md).
Ниже сохранено историческое описание пакета на исходных базах.

# Проверенные исходные дополнения к свежему upstream

Шесть reviewed source patches поверх актуальных upstream commits. Прежние
25 патчей из [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60) и
[PR61](https://github.com/Qweasd123tg/proteus-modules-dot/pull/61) уже перенесены
в upstream: **повторно применять их не нужно и нельзя считать prerequisite**.
Delivery repo остаётся отдельным хранилищем патчей; его baseline —
`73d438d49be6ef15307abb179d1beaa6cbeb7312`.

**`success-evidence: false`**: source review и статическая композиция не
подтверждают успешную компиляцию, тесты, runtime, CI или измеренный выигрыш.

## Что меняется

| Патч | Изменение и сохранённая граница |
|---|---|
| `core/01-derived-only-streaming-reads.patch` | Пять derived-only путей journal больше не удерживают отдельный `Vec<JournalRecord>` и не строят неиспользуемые результаты полной projection. Все records/blob проходят прежний scanner и authoritative validator; поздняя storage error сохраняет приоритет над ранней semantic error. Это не incremental recovery и не общий предел памяти validator. |
| `core/02-cancel-before-peer-lease.patch` | Уже видимая отмена получает приоритет перед готовым role permit: не арендуется fresh/resume peer, используется существующий rollback. Отмена после выбора permit и lifetime worktree не меняются. |
| `modules/01-catalog-deadline.patch` | Ожидание coalescing lock входит в существующий 30-секундный timeout каталога. Cache/TTL, OAuth и single refresh сохраняются; timeout остаётся кооперативным. |
| `modules/02-retry-request-template.patch` | Cloneable OpenAI request делит одно JSON encoding внутри retry phase. OAuth refresh создаёт новую phase; non-cloneable stream сохраняет прежний factory path. Encoded bytes живут и во время backoff: меньший RSS не обещается. |
| `modules/03-reader-terminal-reasons.patch` | Readers различают EOF, read error и drain expiry. Остановка readers и exit команды больше не подразумевают полноту потока; сама правка не включает capture. |
| `modules/04-opt-in-exec-source-capture.patch` | В существующем `shell_tools` явно включаемый raw-prefix capture до preview truncation и `read_exec_capture` через прежний tool RPC. Нет второго shell, нового slot, standalone capture-библиотеки, dependency или Cargo pin. |

Source capture по умолчанию выключен. Оператор выбирает directory и limits;
вывод может содержать secrets, а запрошенные ranges доступны configured
host/model pipeline через обычный RPC. Anonymous files/handles относятся к
одной generation, не являются durable artifacts. Quota действует на binding,
не на весь process/RSS; TTL — logical expiry с lazy cleanup, не deletion SLA.
Queue/file failure после spawn не повторяет команду и не подменяет её exit
code. Sealed prefix, range EOF и complete stream — отдельные состояния.

## Базы, порядок и зависимости

Патчи применяются к соответствующим upstream checkout, **не** к delivery repo:

- [Core `b062bb34634bb7de346d898fb326a9e154c6ed69`](https://github.com/Proteus-harness/Proteus-core/tree/b062bb34634bb7de346d898fb326a9e154c6ed69);
- [Modules `3936728a123fa7019fcf90011804314f609ff7d8`](https://github.com/Proteus-harness/Proteus-modules/tree/3936728a123fa7019fcf90011804314f609ff7d8).

Реальная Core dependency Modules остаётся
`1f533a13f20a93bf164f7c8a169553b0b219bb51`; новый pin не выдуман и не требуется
этими патчами. Journal reset/timestamps/owned-renderer теперь входят в базовый
Core, поэтому прежняя четырёхпатчевая цепочка больше не нужна.
Единственная зависимость между новыми патчами: `modules/04` требует
`modules/03`. Остальные пять применяются непосредственно к своим свежим базам.

Проверенный полный порядок — `COMPOSITION.json`: два Core patches, затем
четыре Modules patches в числовом порядке. Перед каждым применением — обычный
`git apply --check --whitespace=error-all`. Zero-context, ослабление whitespace,
forced/three-way/reject application не являются способом разрешать конфликт:
при смене upstream требуется новое source review, а не принудительный перенос.

## Сохранённые изменения владельца

Fresh rebase сохраняет уже перенесённые journal validation, Core refactors,
явное наследование `source.permission_mode()` в `execute_new_session`,
Modules ACK documentation и новые upstream regression sources. Наследование
mode — содержательное upstream исправление прежнего патча, не форматирование;
старая mode patch не должна заменять свежую реализацию. Совместная
композиция сохраняет все темы `docs/reference.md`, без параллельной копии guide.

[Desktop `a316ec34443db3c5469f3868d3d6bdef984dcb75`](https://github.com/Proteus-harness/Proteus-desktop/tree/a316ec34443db3c5469f3868d3d6bdef984dcb75)
и [Extensions `a5a76246f40219161bdc2a7d7821929ef607d031`](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/a5a76246f40219161bdc2a7d7821929ef607d031)
также уже содержат прежние scoped optimizations. Новые inline-math/typography
features и связанные tests/docs не заменяются старыми патчами. Дополнительных
Desktop/Extensions patches здесь нет; Desktop `repositories.json` уже закрепляет
все три свежие upstream revisions. Это source compatibility review, не UI gate.

## Evidence и следующие gates

`SOURCES.json` содержит source identities, frozen patch hashes и отдельные
preimage/candidate hashes. `COMPOSITION.json` фиксирует строгую цепочку только
этих шести патчей, pre/post hashes и обратное восстановление. `DEPENDENCIES.json`
содержит оставшиеся реальные зависимости, `VALIDATION.json` — статические
результаты и границы, `SHA256SUMS` — весь пакет кроме самого checksum-файла.

Regression sources присутствуют, но успешного executable evidence для этих
изменений нет. Нет измеренных CPU/RAM/latency цифр. Публикация исходников не
означает deployment, готовую portable-сборку или выполненную проверку продукта. Formatter не является compiler/test gate.

Для исполняемой проверки нужны существующие scoped gates: Core journal /
session-store / read-model и process-agent admission/reuse; Modules model-pack,
shell-tool и affected independent/aggregate process fixtures. Для затронутых
wiring/contracts — применимый full/module-swap gate из действующих
[Core testing rules](https://github.com/Proteus-harness/Proteus-core/blob/b062bb34634bb7de346d898fb326a9e154c6ed69/docs/development/testing.md)
и [Modules rules](https://github.com/Proteus-harness/Proteus-modules/blob/3936728a123fa7019fcf90011804314f609ff7d8/AGENTS.md).
Правила остаются у существующих owners; этот README — инструкция доставки,
не новый нормативный guide, framework или параллельная конфигурация.
