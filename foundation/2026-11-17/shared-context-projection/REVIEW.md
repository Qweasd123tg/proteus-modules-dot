# Независимое review

17 ноября 2026. Review выполнено отдельно от автора изменения.

## Подтверждение проблемы

Проверены OpenCode request bridge, pinned Core `ContextChunk` и таблица
`ContextChunk.render_mode` в `docs/architecture/pack-contracts.md`, существующие
Rust/Pi formatters и context producer. OpenCode действительно теряет
обязательную source annotation для нормального default режима, а не только
для искусственного невалидного входа.

## Candidate

Блокеров не обнаружено:

- Общий семистрочный formatter соответствует SourceAnnotated/Verbatim
  контракту; metadata не определяет режим.
- Null и пустой path различаются как в Rust. Изменение прежнего Pi на пустом
  path явно задокументировано.
- Unicode и CRLF/LF сохраняются; input DTO не мутируется.
- Старый fixture теперь содержит обязательные поля с явным verbatim;
  существующие assertions не ослаблены.
- Оба installer уже включают shared directory. Pi compaction и model adapter
  сохраняют доступность через существующий `piMessages` layout. Прямой
  зависимости implementation от implementation не добавлено.

Reviewer независимо выполнил два targeted test files закреплённым Node
24.12.0: **17/17 PASS, zero skipped**.

Review не запускало полный installer/portable, полный Pi suite или
HTTP/process/auth fixtures. Счётчик повторного запуска не прибавляется к
числу уникальных tests. Instruction priority намеренно оставлена вне patch.
