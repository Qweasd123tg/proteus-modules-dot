# Независимый source review: bounded file-read UTF-8

## Verdict

Exact candidate не имеет найденного source-level blocker. Общий borrowed decoder выражает реальный небольшой invariant двух raw-byte read paths, а не искусственное обобщение. Известный read_many malformed EOF defect исправляется без смешения с shell lossy-stream policy. Source acceptance не означает compile/test/runtime PASS.

## Boundary correctness

read_many читает limit+1 bytes, и только bytes.len()>limit разрешает отбросить incomplete tail на искусственном byte cut. Если фактически получено <=limit, включая equality, decode строгий. Старое original_bytes используется лишь для консервативного truncated metadata и больше не доказывает наличие прочитанного budget boundary. При stale larger metadata короткий malformed EOF теперь ошибочен, короткий валидный текст остаётся успешным с прежним truncated=true. I/O errors по-прежнему возвращаются до decode. Public limits ограничены значительно ниже usize::MAX, поэтому saturation не влияет на этот production path.

Helper допускает только Utf8Error.error_len()==None при caller-provided budget flag. Invalid interior, overlong и surrogate bytes остаются ошибками. Он не проверяет невключённый suffix и не обещает, что обрезанный prefix имел валидное продолжение в оставшейся части файла. Нулевой content budget может вернуть пустой bounded prefix без проверки остального файла, как и раньше; это не full-file UTF-8 validation.

read.rs сохраняет точное прежнее условие `end < line.len() || !complete`. Возвращённая длина text заменяет прежний end=valid_up_to, поэтому range truncation reason, line count, output prefix/separator и error formatting сохраняются. **Оговорка:** complete=false при read==allowance без LF, даже если physical EOF случайно ровно на allowance. Этот прежний range path не доказывает observed EOF, поэтому здесь разрешение incomplete suffix остаётся. Нельзя заявлять strict physical EOF rejection для всех modes на любых размерах. Малые фактически наблюдённые EOF cases и read_many limit equality действительно строгие.

read_full остаётся owned String::from_utf8 без лишнего copy. Для уже валидного rendered String fallible raw decoder заменён char-boundary truncate: результат тот же prefix, отсутствует только невозможная UTF-8 error ветка и лишняя allocation. rendered.len()>budget гарантирует корректный начальный index; уменьшение до 0 всегда безопасно. Metadata возвращённых bytes и truncated сохраняется.

## Compile-shape и proposed tests

crate-private read_text module зарегистрирован в lib.rs; decoder borrow lifetime однозначно связан с единственным slice reference. В range borrow живёт пока line неизменён; read_many делает одну ownership conversion до освобождения bytes. Child modules read_many/utf8_tests.rs и tests/read_utf8.rs подключены корректно, private imports/helpers доступны через super::*. FileRead уже имеет Debug, поэтому unwrap_err корректен по type shape; tempfile и invoke harness уже используются в existing tests. Новых dependencies/public contract нет.

Прочитаны семь proposed tests: два helper tests (2/3/4-byte splits, borrowed valid input, invalid sequences); два read_many tests (EOF equality/stale metadata, real budget cuts и conservative metadata); три ToolModule invoke-style tests (четыре read variants, raw prefix cutoff, numbered rendered String cutoff). Fixtures корректно различают malformed EOF и budget split. Это test source, не выполненные assertions. ToolModule tests используют временные files при будущем запуске; в review эти files/tests не выполнялись. Нет large exact-allowance range regression или concurrent file mutation доказательства.

## Scope и evidence

Изменён только UTF-8 read policy и valid String truncation. File authority, edits/concurrency и прочие соседние подсистемы не аудировались. Patch не обещает whole-file validation при bounded/ranged read и не изменяет shell PR115 replacement behavior.

Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531. Coordinator text apply verification не является compile proof. Reviewer прочитал exact patch и relevant caller bounds/line handling, самостоятельно пересчитал:

- patch: 61f6e9e6b1ec75e4237fdf041445382bb7f1955138b9739d914c3da5b718bccd
- read.rs: ae2687e56e5b657cf6aade1b5bcaae40c74dd96fafec4ac9475b94a7817361ea
- read_many.rs: 4e029b68b5a7ac6a1d504c1d664f4e6df27274f205568c72d69be799901c7ac6
- read_text.rs: b578eb13306feb92a014403726ae0afd60e77a8b88f7272a4f916a83aa33496b
- read_many/utf8_tests.rs: 221394eb5c087337992ab0a09eba68a908cd33ced50754adc9d6c69e56f8efc4
- tests/read_utf8.rs: 3f3a281df623001d0ac8a135322cfcea16a92e401878d7ff0af3ce62370f46d8

Rust/compiler/formatter/tests/runtime/project scripts/dependency installs не запускались. Production, refs и публикации не менялись. Runtime performance не измерялся; наблюдаемое удаление лишней allocation на valid rendered truncation — source observation, не benchmark.
