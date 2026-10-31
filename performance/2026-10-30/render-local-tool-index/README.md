# Временный lookup карточек tool при rendering

**Source-only candidate; compilation/tests/runtime не выполнялись.**

Base: [Proteus-core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`](https://github.com/Proteus-harness/Proteus-core/commit/befd30516aefa6f0a0ad5db9924ad4957160b8dc).
Patch применяется к этому upstream checkout, не к delivery-репозиторию.
Ранее перенесённые reset-frontier, scoped timestamps, consuming renderer и
derived-only reads не дублируются.

## Изменение

[Patch](05-render-local-tool-row-index.patch) заменяет повторный обратный проход
по transcript для каждого result/resolution на один приватный render-local
`call_id -> последняя строка`. Canonical и journal renderer используют прежние
общие helpers; новых config, публичного API или persistent cache нет.

Для batch вызовов с поздними результатами прежний поиск мог повторять проход
по строкам для каждого результата. Новый lookup имеет ожидаемую постоянную
стоимость без учёта hashing ID; построение индекса линейно по добавляемым
tool cards. Это алгоритмическое наблюдение, не измеренный speedup.

**Цена — дополнительная временная память:** String key, индекс строки и
HashMap capacity на каждый различный rendered call ID. Lookup сбрасывается
вместе со строками и уничтожается при возврате готового Vec; capacity может
сохраняться до конца одного rendering. Снижение RAM не заявлено. Borrowed keys
потребовали бы self-referential владения rows либо удержания уже потребляемых
records; здесь используются обычные owned IDs без unsafe/lifetime framework.

## Сохранённая семантика

- Каждый append tool/hosted/standalone-result card обновляет lookup; при
  повторном ID выбирается последняя карточка, как при прежнем reverse scan.
- Result/resolution не меняют call identity или позицию строки; reset очищает
  rows и lookup вместе. Compaction/live Replace сохраняют прежнее поведение.
- Citation сохраняет отдельный поиск по текущим name/provider_hosted metadata;
  matching card без массива citations не заставляет искать более раннюю.
- Image attachment остаётся last-row-only; timestamps и interruption finalization
  не меняются. Global visibility, поздняя видимость response и final-result
  suppression не затрагиваются.

Новые regression sources покрывают delayed results через 128 interleaved
calls/text rows, hosted/ordinary collision, metadata replacement, null citation
array, reset/standalone result и allowed/denied resolution. Старые journal
prefix/live/compaction/timestamp scenarios остаются подключены.

## Проверки и ограничения

[SOURCES.json](SOURCES.json) содержит immutable upstream identities;
[REVIEW.md](REVIEW.md) — независимый source review без обнаруженного blocker;
[SHA256SUMS](SHA256SUMS) фиксирует точные доставленные bytes.

Автор и независимый reviewer проверили strict forward/reverse patch application,
точное совпадение candidate и восстановленного baseline. Автор сверил семь
baseline Git blobs с pinned upstream. Diff whitespace check и прямой rustfmt
`--check --edition 2024 --config skip_children=true` прошли для семи изменённых
Rust files. Форматирование не является type-check.

**Compilation, tests, products, Cargo/build scripts, CI и benchmarks не запускались.**
До интеграции необходим применимый `proteus-core --lib app_server::transcript`
gate через штатный runner, включая journal tests. Выигрыш нужно измерить на
delayed-result и обычных immediate-result histories с учётом новой памяти.

Это не incremental projection между чтениями: strict parse/global facts остаются
полными, citations по-прежнему ищутся обратным проходом. Между чтениями нужны
отдельно доказанные prefix identity, late-fact invalidation и bounded ownership;
новая скрытая session cache здесь не вводится. Upstream/main не изменены.
