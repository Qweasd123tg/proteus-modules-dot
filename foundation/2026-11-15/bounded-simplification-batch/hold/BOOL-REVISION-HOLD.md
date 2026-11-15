# HOLD: revision по факту вставки, не по PartialEq

**Отдельное предложение изменения поведения, не полностью эквивалентный refactor.** Patch `02-insertion-driven-revision-HOLD.patch` меняет только `runtime/checkpoint.rs`, +6/−11 строк. Он не обязателен для tuple-only оптимизации.

## Исправление прежнего вывода

Исходный combined report ошибочно распространял эквивалентность `history != previous_clone` и `record() -> bool` на все CanonicalMessage. Независимое review выявило контрпример. Безусловное утверждение эквивалентности отозвано, варианты разделены.

`CanonicalMessage`, `CanonicalPart`, `ContentPart` и `ContextChunk` используют derived PartialEq. `ContextChunk.score` имеет тип `Option<f32>`, а `with_score` просто присваивает значение без finite-проверки. Native значение `Some(f32::NAN)` не равно своей копии. Дополнительная такая поверхность есть у file-search hit `score: Option<f64>` внутри HostedToolActivity.

Поэтому **если live in-memory history содержит NaN**, unbound result не изменяет историю, однако старое сравнение с deep clone всё равно истинно и revision увеличивается. Новый bool остаётся false, и revision не увеличивается. Аналогично непустой batch только из unbound effects. Это source-level counterexample, не воспроизведённый wire/provider инцидент и не доказательство, что обычный process runtime доставляет NaN через JSON.

## Предлагаемая семантика

Revision в этих двух in-memory путях отражает вставку сообщения через HistoryCapture. Не-рефлексивность содержимого сама по себе больше не считается изменением.

`HistoryCapture::record` уже возвращает true только после вставки ровно одного сообщения, false при отсутствии binding, Err до вставки данного результата. Для историй с рефлексивным PartialEq это сохраняет прежнюю логику. Для NaN no-op это **сознательно иное поведение**, которое нужно квалифицировать отдельно.

Убираются две полноисторические clone/equality операции под locks. В batch `changed |= record(...)?` не short-circuit: все элементы обрабатываются. После успешного batch increment остаётся один, для final bound result один; durable revision остаётся у SessionStore. Lookup, ordered insertion, raw-effect retiring, locks и await boundaries прежние.

Поздняя ошибка batch после ранней вставки по-прежнему возвращается до revision increment. Этот существующий путь не исправляется и не объявляется атомарным. Нельзя продавать кандидат как устранение всех revision/recovery проблем.

## Что блокирует снятие HOLD

1. Принять конкретную semantics: revision меняется по факту вставки, а не incidental non-reflexive payload comparison. Документация предложения не является production policy decision.
2. Проверить эту семантику executable native in-memory boundary case: unbound NaN, обычный unbound, bound result, batch с несколькими bound/unbound результатами и сохранённый late-error outcome. JSON-only fixture не доказывает NaN-case: сериализация может не сохранить native NaN. Сначала расширить подходящий существующий Rust case, не создавать второй framework.
3. Пройти применимые existing runtime/checkpoint tests на окончательном коде. Existing `preparation_checkpoint_rejects_stale_revision_and_unbound_tool_does_not_advance_it` уже проверяет обычный no-op в persist=false/true, но **не** NaN и **не** всю batch matrix.

Новых tests сейчас нет. Прочитанное существующее покрытие не выдаётся за executable proof нового поведения. Отдельная Python-имитация алгоритма не добавлена: она не заменит Rust/typed runtime boundary.

## Источники и статические проверки

Core `a3b82a676aa66a7a6b392dc45a29560590fd9b61`. Target checkpoint blob `5aa717381e5e51de30a4f281a888ada7220b790c`; score/PartialEq source identities указаны в [общем SOURCES.json](../SOURCES.json). Strict git apply/reverse, exact candidate/base bytes и GNU zero-fuzz/no-offset проверены. Комбинация с tuple-only patch source-коммутативна, но это не снимает HOLD.

Rust/Cargo/rustfmt отсутствуют. Compilation/tests/runtime/benchmarks/CI NOT RUN. No measured CPU/latency/RSS gain. Upstream не изменён. Это файл для review возможного изменения, не инструкция применять его вместе с первым patch.

SHA-256 patch: `6265beec1edda9e23f0fa8adbafb0ed4c5bbb2dc5cea4c95f5817f83fd86e311`.
