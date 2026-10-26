# Validation — 2026-10-25 UTC

## Итог текущего исходного кода

**29 behavior tests + 1 actual-binary wire test passed; 0 failed/ignored.**
Команда локального прогона:

```sh
cargo test --offline --locked -j2 --manifest-path Cargo.toml
```

Команда, exit 0 и данные контроля ресурсов (пути среды нормализованы):
[`validation/result.json`](validation/result.json). Вывод с нормализованными путями:
[`stdout`](validation/stdout.txt), [`stderr`](validation/stderr.txt).

- Rust 1.95.0; exact Proteus SDK Git pin `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`.
- Хеши сохранены в [`validation/source-hashes.json`](validation/source-hashes.json)
  сразу после прогона. Перед запуском исходники были заморожены; после receipt
  менялась только документация/evidence, не Rust source, fixtures или lockfile.
- `CODE.sha256` — current source/manifest hash snapshot, сверенный с build receipt.
- Этот локальный прогон использовал cache/shared target и ограничение `-j2`.
  Minimal observed free bytes в receipt: 1230782464; reserve 1073741824 соблюдён.
  Эти числа — operational guard, не benchmark/измеренное ускорение модуля.
- Final `cargo fmt --check` после последнего test-only добавления прошёл с exit0,
  проверен 2026-10-25 23:22 UTC. Логи:
  [`fmt.stdout`](validation/fmt.stdout), [`fmt.stderr`](validation/fmt.stderr).
  Для formatter check сборки не запускались.
- JSON research vectors/SOURCES manifest валидны; host.example.toml разбирается,
  обе export configurations совпадают, каждый примерный component содержит
  ровно один export. Это static config check, не successful host launch.

## Что действительно проверяют tests

`behavior.rs`: explicit roots/namespaces, namespace aliases, source pairing при
одинаковых bytes, exact disabled ID до чтения существующего oversized malformed
файла, lenient/strict diagnostic isolation, fences/CRLF/EOF, duplicate keys,
metadata limits/retention, non-UTF8, aggregate/file/count budgets, body-only change
и recovery, `disable-model-invocation`, cancellation/check failure, symlinks,
actual tool call/result identity, default-host-compatible output bounds.

Targeted catalog regression создаёт **16 valid SKILL.md** с длинными license
fields: raw JSON text >200000 bytes, а прежний serialized-result cap256KiB ещё
не сработал бы. Новый cap128KiB даёт точную domain error до default Core truncation.
Отдельный valid file с JSON escaping проверяет load-output cap; меньший escaping
case успешно возвращает полный parseable JSON. Более низкий host output budget
всё ещё может обрезать ответ; это явно указано в README.

`wire.rs`: действительно запускается **наш** executable и SDK wire-v3. Один
process объявляет provider/v4 и tool/v6, оба host-owned OrderedMany; проверяются
provide/catalog/list/load/refresh, canonical raw_arguments, call_id, disabled,
stale digest, missing catalog_path, wrong tool, metadata override rejection.
Fixture host синтетический, сети/model API/чужих server processes нет.

**Это не real Core end-to-end.** Проверка SDK framing не доказывает config loader,
production ToolRegistry/admission/journal path или реальную model tool selection.
Отдельная интеграция с Core в этот результат не входит.

## Сохранённые промежуточные ошибки

- [Первый behavior прогон](validation/initial-behavior.stdout): 25 passed / 1 failed.
  `split_frontmatter` helper пропускал oversized YAML до уже существующей проверки
  в `parse`; helper получил точную собственную closing-fence bound. Не заявляется,
  что production parse принимал oversized frontmatter.
- [Первый wire прогон](validation/initial-wire.stdout),
  [stderr](validation/initial-wire.stderr): неверно авторизованный **fixture** binding
  Tool SelectOne; pinned SDK корректно отверг его. Fixture исправлен на OrderedMany.
  Это не дефект Core/SDK и не основание менять host composition.
- После review усилены source binding и duplicate-key assertions; отдельный tool
  text cap согласован с известным default host budget. Итоговые tests выше
  относятся к исправленным bytes, прежние ошибки не скрыты/не переименованы.

## Не запускалось / не доказывается

Чужие harness suites/servers/scripts, реальные model API, Windows/macOS runtime,
restricted-sandbox conformance, hostile ancestor-rename race, full directory
snapshot/reference-file digest, полный workspace gate, реальный Core invocation
этой новой пары. Нативный `/skill` routing и foreign hooks/templates не реализованы.
Research report и MCP vectors — отдельный source-analysis artifact; 30 tests
этого модуля не считаются динамическими MCP reproductions.

Пути временной среды в публикуемых логах заменены относительными обозначениями; исходный вывод сохранён отдельно. Нормализация не меняет код или результаты тестов.
