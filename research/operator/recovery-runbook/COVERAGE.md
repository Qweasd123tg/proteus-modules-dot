# Покрытие и пределы

## Что сделано в этом пакете

- **40 exact Core Git source objects**, pin `1fc3ef223d10322815dd9290a50d045bc95402bb`, **52 selected read ranges**. Retained source остаётся на месте; новые upstream copies, imports и execution отсутствуют. SHA-256 всего файла подтверждает byte identity, а не чтение каждой строки.
- Прослежены HTTP read dispatcher → query/session lookup → live snapshot либо historical store/projection → response DTO; отдельно CLI parse → early eval branch / execution-bearing replay branch. Для каталога/SSE прослежены конкретные cache/event побочные действия.
- **14 documented surface rows**: A01–A10 и X01–X04. Это число строк, не число unique endpoints и не runtime test count; A08 включает две формы. Existing R39 classifier — отдельно описанный consumer, не Core command.
- **17 immutable input bindings** к R20, R36, R39, R40 и их reviews. Это reuse точных принятых выводов, не новая полная независимая перепроверка каждого старого отчёта/source tree.
- Исторический environment-bound `check_sources.py` (не включён в public-copy пакет) проверял байты против pinned local Git objects, диапазоны, input hashes, Markdown links и присутствие точных literals в выбранных источниках. Это authored static consistency checker, **не Rust parser/compiler, endpoint invocation или semantic proof**.

## Какие слои не заменять друг другом

| Источник | Достоверно в этом scoped study | Что остаётся неизвестным |
|---|---|---|
| Core source pin | Существование форм и прочитанные branch semantics | Actual deployed binary/config, live session contents, timing and race outcomes |
| Live activity/pending | Производимый формат current snapshot | Durable история старых request ACK; внешние effects |
| Historical strict projection | Canonical linkage/record lifecycle validation path | Atomic snapshot нескольких файлов; физический результат внешней операции |
| `/analysis`/transcript | Удобные presentation projections | Effect-only versus final-result provenance — presentation её теряет |
| Eval/replay | Специфический aggregate/report meaning | Выполнение пользовательской цели/полнота проверки |
| R39 prior controls | Ранее принятые 54 pure controls + 3 synthetic CLI самого classifier | Настоящий Core report producer, replay execution или authenticity |

**В этом пакете не выполнены:** все 10 G01–G10 gates, CLI/HTTP обращения, чтение пользовательских сессий, Core/module/provider execution, reload/resume/replay, model/tool/API calls, новые builds, network transmission или publication. Static source checks не увеличивают прежние Rust/runtime counts. Старый baseline90 и frozen Round1–9 reports не изменены.

## Практический результат

Не новый ledger/утилита, а порядок операторских решений и точная граница существующих read surfaces. Две маленькие host/app seams остаются proposals:

1. Correlated durable submission outcome lookup: existing active/last/pending недостаточно для любого старого request. Контракт дедупликации/retention ещё не задан; автоматический retry здесь не реализован.
2. Read-only canonical recovery presentation: существующие records дают effect/final различие, но current analysis/transcript его схлопывают. Нужен host-owned consumer с явной authorization и bounds, не module доступ к hidden files. Реализации нет.

Это не сообщение о воспроизведённой уязвимости, не обещание exactly-once/rollback и не доказательство отсутствия иных read APIs за пределами выбранных dispatchers.

Public-copy layout отдельно не выполнялся. Original accepted report/source/review identities указаны в [PROVENANCE.md](PROVENANCE.md); link/hash parity новой адаптации не является повторным source audit.
