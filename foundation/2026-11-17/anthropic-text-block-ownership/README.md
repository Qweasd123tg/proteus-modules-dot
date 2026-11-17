# Anthropic: text block владеет своим streaming-фильтром

Проверенный Rust-кандидат для Proteus-modules `b7e3ca3`, не установленный runtime и не upstream merge. Публичный контракт, Cargo pins, priority policy, процессы, HTTP и авторизация не меняются.

## Практический дефект

`AnthropicStreamState` держал один `DsmlStreamFilter` на всё сообщение, а `content_block_stop` ничего не делал. Фильтр временно удерживает суффиксы `<` и `</`, поскольку они могут стать началом DSML-маркера. Это затрагивает обычный текст, не только DSML:

- Text `x <`, stop, Text `y`, stop превращались в `[Text("x"), Text("<y")]` вместо `[Text("x <"), Text("y")]`.
- Если за таким Text следовал tool block, terminal fallback дописывал суффикс после tool как новый Text. Порядок canonical parts менялся.
- Незакрытый DSML tool block внутри первого text block подавлял независимый следующий text block целиком.

Первые три regression tests действительно запущены на прежнем production-коде: **0 PASS / 3 ожидаемых FAIL**. Это не доказательство частоты таких live-ответов и не оценка качества вывода модели.

[Контракт Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) определяет отдельные start/delta/stop для каждого content index, соответствующего позиции в итоговом content array. Владелец состояния здесь content block, не сообщение целиком. PR112 исправлял стартовые данные, но прямо оставлял pending/finish policy и multi-block coverage вне scope; это не повторная публикация того исправления.

## Изменение

Состояние фильтра перенесено в `AnthropicBlock::Text` рядом с его буфером. Start и delta используют этот фильтр; stop дописывает удержанный literal suffix в тот же блок и выдаёт TextDelta до следующего блока. Повторный stop не дублирует текст. Terminal fallback для отсутствующего stop тоже дописывает суффикс в исходный блок, а не выбирает произвольный последний.

Новые abstractions или зависимости не нужны. Единственный дополнительный helper объединяет формирование TextDelta для append и flush. Batch sanitizer, trimming и алгоритм распознавания DSML не меняются. В `sanitize.rs` добавлены только Debug/Clone derives для поля enum.

Вне валидного протокола text_delta к отсутствующему/non-text block теперь игнорируется: раньше он мог публиковать текст без canonical владельца. Это явное сопутствующее изменение покрыто отдельным тестом, а не заявляется полной валидацией malformed streams. Missing-stop fallback сохраняет canonical text, но не обещает полное совпадение display deltas для неправильной трассы.

## Проверка

На Rust/Cargo 1.95.0, Linux x86_64, с неизменёнными lock/pins:

```sh
python3 scripts/test.py -p model-pack --lib adapters::anthropic::stream:: --offline
python3 scripts/test.py -p model-pack --lib adapters::anthropic::tests:: --offline -- --skip provider_config
```

- **13/13 PASS**: 7 новых tests + 6 прежних start-block tests. Независимый reviewer повторил final 13/13.
- **26/26 PASS**: прежние pure request/response/state/sanitizer tests, исключены provider_config tests. Тест с `http_200` в имени вызывает только parser/classifier, HTTP не выполняется.
- Новые проверки: literal `<`/`</` до ToolCallDelta, message identity, content order, два text blocks, независимость незакрытого DSML, idempotent/unknown/non-text stop, missing-stop fallback, invalid-owner delta, все UTF-8-valid двухчастные разбиения четырёх выбранных строк.
- Scoped Clippy завершился с exit 0 и 4 warnings в неизменённых OpenAI files; это не warning-free lint pass.
- Patch: strict apply на чистый exact upstream, совпадение трёх файлов с candidate, reverse до точного чистого baseline. `git diff --check` и rustfmt нового test file PASS.

Точные результаты и ограничения находятся в `VALIDATION.json`; независимый review в `REVIEW.md`.

Не запускались full workspace gate, HTTP/provider/auth/process fixtures, live inference, UI/Desktop, portable/package install, Core tests или hosted CI. `proteus-core` только компилировался как закреплённая test dependency. Не утверждается готовность всего продукта к выпуску. Размер фильтра теперь учитывается на каждый text block; RSS/allocations/скорость не измерялись и улучшение производительности не заявляется.

## Применение

Применять только `anthropic-text-block-ownership.patch` к указанному Modules baseline. Core contract не изменён. Existing start-block/recovery repairs уже входят в baseline; старые patches повторно не накладывать. После upstream-интеграции отдельно нужны разрешённые wider gates и сборка соответствующего runtime; эта публикация их не заменяет.

Priority drift остаётся unresolved: данная работа не выбирает семантику InstructionBlock.priority и не меняет порядок инструкций.
