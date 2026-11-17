# Rust-квалификация существующего terminal-reader cut

Дополнение от 2026-11-17 к [PR165](https://github.com/Qweasd123tg/proteus-modules-dot/pull/165),
не новая находка и не копия патча. Исторические source-only результаты пакета
сохранены. Квалифицирован только
[`modules-single-terminal-reader.patch`](patches/modules-single-terminal-reader.patch).
**Upstream production и установленное приложение не изменены.**

## Что действительно упрощается

В `model/model-pack/src/adapters/openai/stream_state.rs` у
`translate_non_message_event` ровно один production caller: wildcard arm
`OpenAiStreamState::translate`. Ветка `response.completed` обрабатывается раньше
через `finalize_completed_event`. Поэтому второй terminal reader внутри helper
недостижим. Удаляются только эта ветка, неиспользуемый import, уточняется комментарий.

В `stream.rs` 4 добавленных / 22 удалённых строки, net **−18**. Это сокращение
неиспользуемой реализации, а не устранение второго реально выполнявшегося parse.
Ускорение и экономия памяти не заявляются. Значимые проверки не удалены:
живой finalizer, terminal error precedence, `incomplete`/`failed`/`error`,
идентификаторы, repair и nonstream parser остаются прежними.

Не добавлен ни один тест «на наличие проверки»; существующие тесты, их названия
и assertions не менялись. HTTP fallback-test cleanup из PR165 и HTTP/auth
кандидат PR166 не входят в эту квалификацию. Остальные кандидаты и HOLD не затронуты.

## Точная база и воспроизводимость

- Modules main: `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.
- Фактическая Core dependency Modules: `185225a7103088c444788374ca425d230060f55a`.
- Core main при сверке: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
  Тесты не выдаются за прогон Modules с этим более новым Core.
- Dot base: `5490522825301e885933013d427061b55ef7b094`.
- Исходный patch SHA-256:
  `2874d5275ec4f9a761ab736ce5706d81288cf6e9b9b04c2de6343c850d38f275`.
- `stream.rs` до: `1518a04aecca5fa4852d8cbf7b268ea45bf06c60c4249efd30796168dfe31e30`;
  после: `436a50f0c225844ec2f4225a0440a173e140cd8f5f4a31820070ca719face8d8`.

На отдельной рабочей копии точной базы сначала выполнен baseline. Затем применён
существующий patch без правок и выполнены те же команды. Cargo.toml, Cargo.lock
и `.cargo/config.toml` не менялись. Никаких dependency overlays или новых pins.
`git apply --check --whitespace=error-all`, reverse applicability и
`git diff --check`: PASS. Единственный изменённый tracked source: `stream.rs`.
Полный участок от `finalize_completed_event` до конца файла byte-identical базе.

## Реально выполненные проверки

Rust 1.95.0, Cargo 1.95.0; штатный runner использует закреплённый Core dependency.

```sh
python3 scripts/test.py -p model-pack --lib adapters::openai::stream::tests --offline
python3 scripts/test.py -p model-pack --lib adapters::openai::tests::translate_sse_ --offline
rustfmt --check --edition 2024 --config skip_children=true model/model-pack/src/adapters/openai/stream.rs
```

| Scope | Baseline | Exact patch | Независимый повтор |
| --- | --- | --- | --- |
| Finalizer | 6 PASS, 0 FAIL | 6 PASS, 0 FAIL | 6 PASS, 0 FAIL |
| Stateful dispatch | 11 PASS, 0 FAIL | 11 PASS, 0 FAIL | 11 PASS, 0 FAIL |

Каждый finalizer run отфильтровал 177 других тестов, dispatch run 172.
Это **17 существующих уникальных тестов**, а не 51 новое покрытие.
Имена выполненных тестов до/после совпадают. Changed-file rustfmt: PASS.

Finalizer cases проверяют authoritative output без streamed reconstruction,
однократную lazy reconstruction, stable replacement/append order, terminal error
precedence, cache usage missing vs zero и повторную terminal repair.
Dispatch cases проверяют completed response, text/reasoning/function/custom-tool
deltas, error/failed/incomplete, actionable context-window error, unknown event
и `[DONE]`. Это pure synthetic JSON/state проверки, не сетевой provider run.

## Независимый review и границы вывода

Отдельный reviewer сверил exact patch/hash, единственный caller, reverse apply,
неизменность живого finalizer, nonstream parser, обоих test files и pins;
прочитал baseline/candidate logs и самостоятельно повторил два exact filters.
Вердикт: блокирующих source-проблем нет, допустима узкая квалификация прежнего cut.

**NOT RUN:** весь model-pack/workspace, broad stream_state suite, HTTP/provider,
process/security fixtures, portable/GUI, packaging/install, benchmarks и CI.
Сборка lib test target не означает исполнение отфильтрованных fixtures.
Это не квалификация всего PR165/PR166 и не разрешение снимать HOLD.
Для upstream adoption остаются применимые интеграционные gates; эта публикация
добавляет только проверенное evidence к уже существующему предложению.
