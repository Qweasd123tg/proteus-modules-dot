# Независимый review: Anthropic start blocks A2/A3

## Verdict

В exact candidate source-level blocker не найден. Узкое исправление известных A2/A3, не новая finding: сохраняется стартовое содержимое text/tool_use, без новой публичной abstraction или изменения terminal policy. Acceptance относится к чтению исходников, не к compile/test/runtime PASS.

## Семантика

- `initial_input: Value` сохраняет input стартового tool_use без stringify/parse. Missing input остаётся Null, как в существующем nonstream parser. На terminal без JSON-байтов значение перемещается в ToolCall; пустые delta не стирают его и не создают synthetic ToolCallDelta.
- Первый nonempty partial освобождает initial input, а отдельный input_json собирается с нуля. Это replacement, не merge и не конкатенация с initial JSON. Дальнейшие пустые delta не возвращают fallback. Пробелы являются nonempty bytes: strict final parse продолжает выдавать прежний Other при некорректном JSON, а не маскировать ошибку стартовым значением.
- SDK Python `accumulate_event` сохраняет start block целиком; text_delta дописывает text, а JSON deltas используют отдельный буфер и заменяют content.input только если буфер непустой. Это подтверждает выбранную boundary. Полная эквивалентность SDK не заявляется: его incremental partial JSON parsing отличается от существующего строгого terminal parse данного адаптера.
- `append_text` буквально сохраняет прежнюю последовательность text_delta: shared DSML filter, append в text block при его наличии, suppression пустого результата, TextDelta с прежними message_id/phase. Start вызывает его после установки блока и только для nonempty text. Это сохраняет фильтрацию между start и delta, включая split marker. Не добавлена новая index/type validation.
- Final sanitization/trim, DSML finish и его прежняя политика pending text не менялись. Поэтому не заявляется универсальное равенство raw delta concatenation и финального sanitized text; proposed text cases проверяют выбранные совместимые примеры.
- Проверка stop_reason остаётся до разбора аргументов: лишь tool_use разрешает завершённые calls. Length/Stop/Unknown не становятся executable от наличия initial input и не начинают разбирать раньше игнорируемые malformed partials. Reasoning, opaque, unknown blocks, usage и message identity не изменены.

## Compile-shape и proposed tests

Новый `#[cfg(test)] mod start_tests` в stream.rs соответствует пути anthropic/stream/start_tests.rs. `super::*` даёт private родительские types; `super::super::response::from_anthropic_response` доступен из descendant anthropic module через существующий pub(super). Дополнительного публичного API или dependency не требуется по исходникам. Borrow parsed block не связан с self; inner shadow `block` заканчивается до чтения start text. Сопоставления ToolUse учли новое поле либо используют `..`. Компилятор не запускался.

Прочитаны все шесть proposed tests: text start/delta и Unicode; DSML split marker; missing/null/empty/object initial input с отсутствующими/пустыми deltas; replacement fragments; malformed/whitespace partials; non-tool stop suppression. Fixtures вызывают настоящий translator и сравнивают payload с nonstream parser без сравнения independently generated message IDs. Tests не выполнялись. Нет live HTTP, полного driver integration, multi-block/interleaving regression или исчерпывающего Value-shape matrix; это предел покрытия, не обнаруженный blocker.

## Композиция

Coordinator сообщил text-only apply/check для семи порядков в COMPOSITION.json, включая explicit PR110-on-PR108 rebase. Reviewer отдельно прочитал combined `108-110on108-new`: anthropic.rs и errors.rs byte-identical ранее проверенному M4 combined-with-PR108; stream.rs отличается от текущего standalone after только известной M4 error-classification веткой. Новый start_tests module сохранён. Следовательно, ownership, eager state construction и HTTP200 recovery eligibility gate не затронуты этим patch. Независимый `diff -qr` подтвердил равенство трёх combined деревьев. Это не compile/runtime composition proof. Original PR108 и standalone PR110 по-прежнему не объявляются автоматически совместимыми.

## Evidence и ограничения

Baseline Modules c035142558f0fca43e9772fc0e50ca293abf1531; provenance catalog 15 sources и apply verification предоставлены coordinator. Reviewer прочитал exact diff, relevant baseline/SDK/combined source и самостоятельно пересчитал:

- patch: `bdd344667c3dc3645487d6dd953032b46214c22ae8515a8eef2122a351f3213e`
- after stream.rs: `6dff0425a4d7aeb8cdec7235f494d463ffa069c5909649a1e547c4929e92bbf4`
- after start_tests.rs: `929be724bd932741fc88ba79955d123b018df7901cc1b71582855b303ed545d5`
- SDK _messages.py: `ced016b069d38d97f343c27a6a6ab462a8831960c6fc97248864a59f8f25e12f`

Не запускались Rust/compiler/formatter/tests/runtime/project scripts/provider calls/dependency installs. Production и публикации не менялись. Не заявляется измеренный performance effect или исправление иных known boundaries.
