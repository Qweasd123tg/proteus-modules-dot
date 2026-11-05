# PR62: все шесть изменений уже перенесены upstream

## Результат

**Неперенесённых implementation hunks из PR62 не найдено. Повторно применять
его шесть патчей к указанным commits не нужно.**

- [Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`](https://github.com/Proteus-harness/Proteus-core/commit/befd30516aefa6f0a0ad5db9924ad4957160b8dc).
- [Modules `200d1ec54f1217f61a31823db939df3799c638dc`](https://github.com/Proteus-harness/Proteus-modules/commit/200d1ec54f1217f61a31823db939df3799c638dc).
- [PR62](https://github.com/Qweasd123tg/proteus-modules-dot/pull/62) на момент
  проверки остаётся open draft, head
  `88222af6ff88b33a46c7aa40c3038ff3c8c70154`, не merged. Upstream port не означает
  merge delivery PR.

Все 12 файлов исходного delivery packet сверены с immutable PR head. Затем
проверены все 42 файла его **итоговой совместной композиции**: 40 совпадают
побайтно, включая все 25 production Rust files. Из 13 regression-source files
12 совпадают; один process fixture улучшен пользователем. Из четырёх документов
три совпадают, один уточнён. Core: 13/13 exact; Modules: 27/29 exact.

## По каждому кандидату

| Кандидат | Статус и сохранённая семантика |
|---|---|
| Derived-only journal reads | **PORTED.** Пять узких путей используют authoritative validator без отдельного all-record Vec; storage/hydration error priority и полные raw/replay/callback paths сохранены. Все пять новых prefix/error/storage regression sources совпадают. |
| Cancel before peer lease | **PORTED.** Видимая отмена приоритетнее готового permit; существующий rollback сохраняет resume reservation. Fresh/resume admission regressions совпадают. Это не решение cancellation после выбора permit. |
| Catalog deadline | **PORTED.** Lock wait находится внутри существующего timeout. Три новых waiter/cache/drop regression sources совпадают; OAuth/cache policy не изменена. |
| Retry request template | **PORTED.** Cloneable request повторно использует prepared body внутри одной retry phase; streaming fallback и новая phase после OAuth refresh сохранены. Encoding/status/error regressions совпадают. |
| Reader terminal reasons | **PORTED.** EOF/read error/drain expiry остаются разными фактами. Сравнение выполнено с итоговым состоянием после source-capture stage, а не с промежуточной stage1. Reader regressions совпадают. |
| Opt-in exec source capture | **PORTED.** Config/schema, existing shell owner, raw-prefix writer, owner/workspace checks, bounded range read, receipts и default-off сохранены. Все production files и unit regression sources совпадают; real-worker fixture получил описанные ниже улучшения. |

Точные patch SHA-256, upstream blob IDs, current-file SHA-256 и публичные URLs
содержатся в `SOURCES.json`; адресный verdict — в `PORTED.json`.

## Пользовательские изменения — сохранить

1. [Process fixture](https://github.com/Proteus-harness/Proteus-modules/blob/200d1ec54f1217f61a31823db939df3799c638dc/components/process-module/tests/independent_modules/source_capture.rs)
   задаёт worker `HOME` равным fixture workspace: обычный пользовательский login
   profile не должен добавлять stderr перед проверяемым raw prefix. Assertion
   дополнительно выводит exec preview при несовпадении bytes. Standalone и
   aggregate cases, catalog/schema parity, exit code 7, receipt, truncation,
   completeness и range-EOF assertions сохранены. Это fixture-local настройка,
   не доказательство полной изоляции от системных shell profiles.
2. [Modules reference](https://github.com/Proteus-harness/Proteus-modules/blob/200d1ec54f1217f61a31823db939df3799c638dc/docs/reference.md)
   явно упоминает yield deadline и exit-drain grace; возврат результата не
   доказывает completeness. Нижний предел capture уточнён: **1 байт**, не 1 MiB.
   Parse и schema уже задают целые bytes от 1 до 64 MiB: это исправление текста,
   не новая конфигурация или изменение runtime limit.

Точная оговорка для будущей документации: в `wait_and_collect` проверка
`readers.is_closed()` находится внутри `output.exited`. Одного закрытия readers
недостаточно для раннего возврата, пока child продолжает работать; yield deadline
остаётся отдельным пределом. Не расширяйте краткую формулировку guide до другого
контракта. Нужды переиздавать implementation patch из этого не следует.

## Что не установлено этой сверкой

**`success-evidence: false`**. Это read/hash/diff/source reconciliation, не
результат compile/tests/runtime/CI/benchmark. Успешный executable evidence этим
проходом не установлен; количественного CPU/RAM/latency вывода нет. Ephemeral
capture, binding-local quotas, lazy TTL cleanup и blocking-I/O ограничения
остаются прежними. Source capture не включался.

Terminal-result ownership, worktree late cancellation и API proposals не входят
в эти шесть кандидатов и рассматриваются отдельно. Внешних записей, merge,
изменений upstream/main или запуска patch code этой сверкой не выполнялось.
