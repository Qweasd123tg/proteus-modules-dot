# Portable update: одна граница snapshot → publication → archive

## Результат

Подготовлен минимальный candidate для **известного PR85 release-manifests №2**, не новая finding: два перекрывающихся partial update одного default destination не должны возвращать невыбранный компонент к старому snapshot.

Используется один Linux advisory lock в стабильном родительском каталоге destination. Он берётся **перед разрешением/чтением базы** и удерживается через copy, assembly, validation, publish, cleanup и archive. Это граница владения всей операцией, а не отдельная блокировка двух rename. Второй participating update с default base читает результат первого.

Фактически выполнено на Python **3.12.14**, `-I -B -S`:

- Baseline: **1 expected regression failure**. Actual `portable.main`/copy/publish в synthetic overlap оставляет `extensions.txt = old` после успешного второго update.
- Candidate: **6/6 focused synthetic tests passed**, без errors/skips.
- Strict patch check/apply и byte comparison успешны.
- Independent contract/pre-run review выполнены; final source/evidence review находится отдельно.

Это не два настоящих build CLI, не реальная portable установка и не full release gate. Два main-вызова работают в разных module instances и потоках с controlled builders; отдельно собственный Python subprocess проверяет только stdlib file-lock exclusion. Cargo, Rust, native CLI, model/API calls и настоящие builders не запускались. Permissions не менялись.

## Pins и дедуп

- Desktop `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Delivery `b58dafbe8a8f1ab85d67139803b1e4c31716816c`, включая несвязанный PR141 argv-identity candidate.
- Пять точных source/doc blobs подтверждены Git blob hashes и SHA256 (`SOURCES.json`, `READ-VERIFICATION.json`).
- Источник известной проблемы: [release-manifests №2](https://github.com/Qweasd123tg/proteus-modules-dot/blob/b58dafbe8a8f1ab85d67139803b1e4c31716816c/research/proteus-continuous-audit-2026-11-13/evidence/release-manifests/REPORT.md). Старый настоящий multi-process build reproduction не повторялся; его результаты не считаются результатами этого прохода.

Предмет этого package: benign update serialization и snapshot correctness. Не исследовались security, process authority, permissions или ранее исключённые направления. Upstream checkout и production не изменялись.

## Причина и общий invariant

В исходном [portable.main](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/scripts/portable.py#L146-L195) read/copy default base выполняется до долгой assembly. [publish](https://github.com/Proteus-harness/Proteus-desktop/blob/7eaf70c67dabba8595d98029c875ffc3f59209ad/scripts/portable_state.py#L133-L148) заменяет весь bundle. Две корректные независимые stage могут поэтому включать устаревшие копии невыбранных групп. Rollback при rename error не предотвращает успешную публикацию stale stage.

Общий invariant: **participating update владеет destination от получения reusable snapshot до завершения его publication-dependent outputs**. Archive тоже читает `PORTABLE`, поэтому освобождение lock сразу после publish позволило бы другому update подменить архивируемую версию.

Candidate не добавляет generation framework, merge machinery или новый manifest format. Он использует существующий `portable_state` для одного context manager и отделяет уже имеющееся тело операции в `_update`. AST-сравнение подтверждает, что тело `_update` совпадает с прежним хвостом main от `base = ...` до archive (`BODY-VERIFICATION.json`). Это статическая проверка сохранения тела, не замена behavioral tests.

## Patch и цена решения

`portable-update-serialization.patch`, SHA256 `503288f21688682efe1c42d0913f3b4faec033faff5a7ba6c1e0fd5412d6006e`.

- `portable_state.update_lock(destination)`: stdlib `fcntl.flock(LOCK_EX)` и закрытие file handle при выходе/exception.
- Стабильный файл `.Proteus.update.lock` рядом с `Proteus` остаётся после release. Его нельзя unlink между владельцами, иначе ожидающие и новые участники могут использовать разные inode.
- Main оставляет parse/argument validation/selection до lock; `_update` включает зависимый `base.resolve`, все прежние шаги и archive.
- `--plan` использует `nullcontext` и по-прежнему возвращается до filesystem writes.
- Документация описывает область гарантий и исключения; добавлен отдельный focused test module.

Production diff: **21 добавленная / 1 удалённая строка** в двух scripts; всё остальное — 12 строк документации и 257 строк tests. Это уменьшение числа независимых publication interleavings, не уменьшение LOC и не ускорение. Цена: participating обновления одного destination ждут друг друга **включая время сборки и архивации**; появляется один постоянный пустой lock-файл. Нет новых внешних dependencies.

## Фактические tests

Тестовый loader исполняет точные `portable.py` и `portable_state.py`, но до import подставляет scoped стандартные `ModuleType` stubs для source/build/limit dependencies и восстанавливает `sys.modules`, включая существовавшие записи. Каждый production module path проверяется. `read_record`, protocol/source validation, source resolver, limiter и assembly заменены явно synthetic helpers. Actual copytree, publish и archive выполняются только над plain files во временных каталогах. Fixtures не являются полноценными runnable bundles.

1. **Overlap regression:** два отдельных module instances, два потока, один owned destination. Первый builder удерживается после создания своей stage. Если lock не удерживается, второй update полностью публикуется до отпускания первого, детерминируя исходный rollback другого компонента. Если lock удерживается, второй объявляет попытку входа, затем первый отпускается и второй использует обновлённую базу. Baseline падает именно на `old != new` у Extensions; candidate сохраняет оба `new`, невыбранные Modules остаются `old`.
2. **Transaction coverage + archive:** отдельный nonblocking open проверяет lock во время base/stage reads, assembly, actual publish и actual tar archive. Архив содержит ожидаемые synthetic Core/Extensions bytes. Сам по себе lock probe не считается lost-update reproduction; для этого отдельно есть пункт 1.
3. **Plan:** при отсутствующем build каталоге `--plan` не создаёт ни его, ни lock и не вызывает base validation.
4. **Builder failure:** synthetic exception оставляет старую базу, удаляет свою stage и освобождает lock, не удаляя lock-file.
5. **Full/reuse controls:** cold full update и explicit external-base reuse проходят через тот же destination transaction; внешний fixture не изменяется. Это не concurrency test внешней базы.
6. **Process lock control:** собственный дочерний Python `-I -B -S` исполняет только reviewed stdlib `fcntl` probe. При удержанном lock получает exit 23, после release — 0; повторный вход сохраняет тот же lock-file inode. Это не настоящий portable CLI process.

Точный baseline target — только overlap regression, candidate target — все шесть tests. Всего семь test executions: один ожидаемо красный, шесть зелёных. Логи, exit codes, expected source hashes и summary сохранены в `runtime/` и `TEST-RESULTS.json`.

Схема запуска:

```sh
HOME="$PACKAGE/runtime/$MODE/home" TMPDIR="$PACKAGE/runtime/$MODE/tmp" \
  python3 -I -B -S "$PACKAGE/run_target.py" \
  "$PACKAGE/runtime/$MODE/scripts" "$PACKAGE/runtime/$MODE-expected.json" "$MODE"
```

`$MODE` — `baseline` или `candidate`. Baseline — точные source bytes плюс тот же новый test file; candidate — exact patch. Драйвер проверяет SHA256 трёх source/test файлов до/после, test module path и точное число выбранных tests. SHA256 драйвера `1fca78ea8efed3c42cd5468602b8d088c9e3e82bec37a6775d870f279a003613`. Никакая сетевая изоляция этим не заявляется; проверенный путь не содержит внешних API-вызовов.

## Ограничения гарантий

- Только **cooperating portable.py invocations одного destination**. Другие writers, удаление lock-file и конкурентное изменение внешнего `--base` не координируются этим patch.
- Explicit `--base` остаётся выбранным snapshot: даже после serialization он может намеренно заменить содержимое destination своей версией. Это не merge текущего destination и не default-base lost-update guarantee.
- Linux/доступная `flock` filesystem semantics. Cross-platform или remote-filesystem behavior не проверены.
- Archive failure **после успешного publish не откатывает уже опубликованный bundle**, как и раньше. Candidate не обещает общую atomicity publication+archive.
- `--plan` остаётся intention-only, не coherent snapshot или validation concurrent bundle.
- Lock может быть создан ещё до base validation. Некорректный non-plan запуск может оставить пустой lock-file/build directory; пользовательские bundle bytes при этом не изменяются до прежней publication стадии.
- Не запускались штатные release tests, builders, runtime validation, native GUI, actual CLI/build concurrency, packaging integration, portable install, benchmark или Rust/toolchain. Исходная проблема не объявляется полностью интеграционно закрытой.

Independent contract и pre-run reviews находятся в `CONTRACT-REVIEW.md` / `PRE-RUN-REVIEW.md`. Итоговый evidence review хранится отдельно. Candidate следует публиковать только с указанными synthetic-gate ограничениями, не как production-qualified install fix.
