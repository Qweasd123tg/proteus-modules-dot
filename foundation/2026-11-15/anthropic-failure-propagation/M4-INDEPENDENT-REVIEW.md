# Независимый source review: M4 Anthropic failure classification

## Итог

**Повторный source review: scope blocker закрыт в актуальном after. Новых source-level blockers не найдено.** HTTP200 eligibility теперь ограничивает новые SSE recovery kinds. Это проверка исправления ранее опубликованного M4, а не новая finding. Не заявляются compilation/test/runtime PASS или проверенное восстановление реального provider request. Prior report относится к прежним запускам и не заменяет проверку текущего патча.

## Точность классификации

- ContextWindowExceeded создаётся только для HTTP400, provider type invalid_request_error и точного сообщения `prompt is too long` либо строки с префиксом `prompt is too long:`. Нет substring matching, trim, case folding или общей классификации всех400/invalid_request_error. `prompt is too longish`, предшествующий текст, другие statuses/types остаются Other. Суффикс после colon намеренно не разбирается как число токенов.
- Retryable с retry_delay_ms=None создаётся только для HTTP529 либо SSE error-event без HTTP status, с overloaded_error и строковым message. Сам по себе HTTP529, неизвестный error type или нестроковый/отсутствующий message не получает retry kind. Пустая строка всё ещё строка и соответствует заданному type-based контракту; это не новый fallback по тексту.
- SSE invalid_request_error даже с exact prompt-too-long message остаётся Other. Не расширяется HTTP-only overflow rule на иной transport context.
- Документированные основания проверены по официальным [context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) и [API errors](https://platform.claude.com/docs/en/api/errors): input overflow относится к400/invalid_request_error, overload к529/overloaded_error. [Streaming](https://platform.claude.com/docs/en/build-with-claude/streaming) описывает отдельные error events и terminal message_stop. Это поддерживает узкие mappings, но не обещает все будущие error shapes.

## HTTP, SSE и ошибки

- Streaming path читает body только для400/529, затем возвращает typed ModelFailure через anyhow::Error::new. Для всех остальных статусов остаётся прежний error_for_status. Direct rejection остальных4xx/5xx сохранён;1xx/3xx по-прежнему допускаются к SSE. Новый stream_failure_kind сохраняет selected kind только для HTTP200, для остальных возвращает Other; он применяется к каждому translated Error и EOF. Поэтому non-200 downstream failures также не получают новую retry/compaction классификацию.
- Non-stream path сохраняет существующее чтение response body и условие !is_success. Diagnostic string остаётся точным прежним `Anthropic API error {status}: {body}`; неизвестные cases получают Other. Внутренний anyhow payload теперь ModelFailure, что намеренно обеспечивает contract downcast; не следует называть внутренний concrete error type неизменным.
- Body-read failure остаётся прежней propagated reqwest error, без выдуманной успешной классификации недочитанного body. Новое whole-body чтение streaming400/529 — реальная дополнительная работа/ожидание; здесь нет измерения её стоимости и не добавляются новые лимиты/хранилища.
- Malformed JSON в SSE по-прежнему Other до decoder; generic eventsource parser/transport Err по-прежнему Other, устанавливает saw_terminal_event и не падает далее в EOF branch. Новый StreamDisconnected возникает только при HTTP200 и чистом исчерпании SSE iterator без terminal response/error; прочие статусы оставляют Other. Текст сообщения EOF сохранён.
- Translator на typed error не вызывает finalise и не переносит partial text в completed_messages. Маппер создаёт пустой список completed messages согласно pinned ModelFailure constructor. Success, Length, tool parsing, message identity и provider output completion не изменены.
- Provider retry не добавляется. send_with_transport_retry остаётся прежним; новый Retryable — только классификация для вызывающего алгоритма, который владеет бюджетом повторов. EOF/overload не превращаются в completed assistant response.

## Проверка proposed test source

Тесты не запускались. По чтению:

- HTTP matrix охватывает positive pairs и другие statuses; сохранение diagnostic, пустых completed_messages, anyhow downcast/context и serde roundtrip проверяется явно.
- Negative cases исключают generic invalid_request_error, substring-like сообщения, unknown type, rate limit, отсутствие/нестроковый message и malformed body. Exact overflow positive и SSE overflow negative присутствуют.
- SSE test использует настоящий AnthropicStreamState: text block + partial delta, затем error. Проверяется единственный Error event, kind/message и отсутствие completed messages. Отдельно проверяется malformed SSE JSON → Other.
- Новая pure matrix проверяет eligibility для101/200/201/204/302/400/529/598 и StreamDisconnected/Retryable/Other. Она не заменяет реальный HTTP/SSE driver test.
- Нет live HTTP/реального stream driver/EOF regression, проверки retry/compaction consumer outcomes, body-read failure или PR108 combined execution. Classifier matrix не доказывает сетевую wiring ветку сама по себе; wiring и EOF branch установлены чтением diff. Tests не являются новым доказательством устранения исторических runtime сценариев prior report.

## Scope и composition

Прочитан весь patch и before/after changed source; actual Core pin `41bdfffa6e70228278b4abc758b7f81a12672f35` ModelFailureKind/ModelFailure прочитан напрямую. Modules baseline `c035142558f0fca43e9772fc0e50ca293abf1531`. Core main/полный blob verification предоставлены координатором, не пересканированы полностью этим review.

PR108 пересекает anthropic.rs по файлу, но изменяет state ownership; этот candidate оставляет baseline Arc/Mutex state. По сообщению координатора direct apply двух original patches конфликтует на соседнем for mapped context в обоих порядках. Автоматическая совместимость не заявляется; отдельный rebased-on-PR108 patch пока не reviewed здесь. Совместный build не выполнялся. Auth и другие вне-scope направления не изменялись и не анализировались. Production, refs и публикации не менялись.

## Независимо проверенные SHA256

- patch: `09c17c0b5ba48e7e715453c3c90a24875e8d288f740eefe4fc1e62e631303ce4` (regenerated eligibility candidate, независимо прочитан)
- after anthropic.rs: `e283f39a453a5a5d4c502be93a9875711ae1270c96f9c7de80c0fcb6cf118fd9`
- after anthropic/stream.rs: `b02d0ed2239982b0cde9a1501b7d6b72c5ef17eaf316a164cc4352a52fc5eb57`
- after anthropic/errors.rs: `ddf0f6c99f278310aee3f2fe723dc9abafcf6d431a5b459632f2bbd368520370`

Rust/compiler/toolchain, tests/fixtures, project scripts/runtime, provider calls и installs не запускались. Выполнены только source reads и собственные text/hash операции.

## Закрытый scope blocker и повторный review

Первый кандидат сохранял HTTP gate, но менял downstream recovery для3xx + EOF/typed SSE overload. Повторный after добавляет небольшой pure stream_failure_kind(status, kind), который разрешает selected kind только для HTTP200. Outer stream loop применяет его к translated Error и EOF. Non-200 canonical Response не модифицируется; typed HTTP400/529 возвращается до stream path. Дополнительной state machine, retries или partial-message promotion нет. Прежний scope blocker закрыт, new blocker не выявлен.

## Отдельный неисправленный boundary: direct Model::complete

Pinned Core default Model::complete обрабатывает Response, но не возвращает canonical Ok(Error) как typed failure; этот известный отдельный MDC-1/PR99 boundary здесь не исправляется. Поэтому не заявляется, что direct Rust Model::complete у stream-enabled client теперь сохраняет SSE typed failure. Ошибки HTTP до создания stream возвращаются через Err и этот предел не имеют. Отдельно прочитан ProviderModule::stream в module.rs: adapter.stream Err превращается в RequestError с ModelFailure::from_error, canonical Ok(Error) — в StreamError с тем же failure. Это source подтверждение process boundary, не выполненный integration test. Основной process stream path и direct complete нельзя смешивать в заявлении о результате.

## Финальный addendum: явный rebase на PR108

Независимо сравнены standalone after и combined-with-PR108. В anthropic.rs ровно три ранее reviewed PR108 substitutions: удаление Mutex из импорта, direct mutable state с прежним eager default до stream!, direct state.translate вместо lockguard. M4 `for mut mapped` и HTTP200 eligibility сохранены. errors.rs и anthropic/stream.rs byte-identical standalone M4 (проверено cmp). Новых source-level blockers в разрешении контекста не найдено.

Прочитан rebased patch context вокруг direct translate; он корректно добавляет mutation результата после owned translate, не возвращая lock и не перемещая default внутрь generator. Hash rebased patch независимо подтверждён: `264ede250e103dc353d9fb630e30217d6ceae34b821ce68cdac894a802a43acf`. Combined anthropic.rs SHA256: `ec85ef09f3d21bf0c02772c1496bd5989aef058f884f2b2fe0e2c144b4b880eb`.

Успешный apply/whitespace check rebased artifact сообщил координатор; этот reviewer отдельно проверил exact source delta и hashes, не повторяя apply. Это ручной явный rebase, НЕ автоматическая совместимость двух original patches: их исходный context conflict остаётся зафиксирован. Ни Rust/build/tests/runtime, ни combined execution не запускались. Standalone verdict и предел direct Model::complete остаются прежними.
