# Независимый exact review: context-stop recovery-only

## Verdict

Source-level blocker в exact candidate не найден. Это узкое исправление recovery известного context-stop family, **не полное outcome/accounting исправление**. Baseline — c035142558f0fca43e9772fc0e50ca293abf1531 плюс standalone PR110; patch не предназначен для заявления clean-upstream apply. Compile/tests/runtime не подтверждены.

## Classification и precedence

Один private provider-local classifier возвращает existing ContextWindowExceeded только для exact HTTP200 и exact model_context_window_exceeded. max_tokens, неизвестный/missing stop и любой иной status не получают новую recovery semantics.

Nonstream сначала сохраняет существующую status handling, JSON decoding и from_anthropic_response errors. Classification вызывается только после успешного decoder по сохранённому provider_metadata.stop_reason. Поэтому provider error envelope, отсутствующий content и другие decoder errors не заменяются context recovery. Status-blind decoder API не изменён; 201/204 с context stop сохраняют старый Length projection. Вызов failure.into() сохраняет typed anyhow failure, не превращает его в string.

Stream production передаёт фактический status в state до создания generator. finalise отдаёт Error до построения Response только eligible HTTP200 context stop. Текущий partial text/tool buffer не повышается до completed_messages: failure по умолчанию пустой. Прежние deltas могли уже выйти, но terminal success не синтезируется. Некорректные tool JSON fragments при context stop прежде также не разбирались, поскольку accept_tool_calls=false; новая early classification не маскирует ранее обязательный parse error в этом пути. Настоящий tool_use с malformed arguments по-прежнему даёт Other. Malformed SSE JSON обрабатывается прежней translate веткой раньше finalise.

PR110 outer stream_failure_kind gate остаётся неизменным. Необычные admitted HTTP statuses сохраняют прежнюю Response/Length/etc форму, а не только понижают новый typed Error до Other. Это важное отличие: outer gate сам по себе не смог бы восстановить Response projection после unconditional finalise Error.

## Минимальность state

Status field и private new(status) оправданы строгим сохранением non-200 terminal shape. Только outer error-kind gate недостаточен; альтернатива передавать status/eligibility в каждый translate/finalise либо выставлять field setter добавляет plumbing или временное default состояние. Constructor оставляет translate API неизменным и не требует обновлять PR112 private append_text calls. Default HTTP200 предназначен для прежних state tests. new(status) вызывает Default один раз, поэтому eager message_id generation сохраняется. Новый DTO/framework не введён. StatusCode — owned Copy value; новых async borrow/Send требований нет.

Иной более короткий вариант возможен с bool eligibility вместо status, но он не доказан существенно проще: actual status уже нужен classifier и помогает явно проверять boundary. Замена ради LOC не требуется.

## Imports/privacy и proposed tests

Полный diff пяти файлов прочитан. errors/stop_tests.rs корректно подключён как child errors; доступ к соседнему stream::AnthropicStreamState через ancestor anthropic pub(super) допустим. Existing parent imports дают ModelFailureKind в anthropic/tests.rs. Constructor видим нужному parent и descendants. Test uses Result/error wrapping APIs уже присутствуют в dependencies.

Четыре новых pure test functions проверяют status×stop eligibility и typed serialization/downcast; partial text+malformed tool delta без completed/Response; unchanged other status/stop/usage projection и normal tool_use parse error; nonstream decoder precedence и metadata. Existing test обновлён с Length stream на typed HTTP200 boundary. Tests не запускались. Nonstream test воспроизводит decoder+classifier последовательность, но не вызывает реальный async HTTP client; stream trace тестирует state, а не live outer driver. Нет выполненного compactor retry integration или accounting regression.

## Scope и остаточные риски

В validated stock path прежний Length уже превращался в Other до durable response usage recording. Здесь восстанавливается actionable cause; accounting gap остаётся. Для direct raw consumers прежний Length Response с usage теперь заменяется typed Error на HTTP200 context stop: нельзя заявлять «usage projection не меняется нигде». ModelFailure не несёт usage. Дополнительные recovery attempts могут оставаться неучтёнными в прежнем durable usage path. Это должно быть частью delivery scope, а не скрытой оговоркой.

Actual старый Core pin default Model::complete всё ещё теряет canonical stream Error; PR111 исправляет это только после соответствующего dependency update. Nonstream startup typed Err и корректные stock wrapper/process paths отличаются от этого raw default boundary. Patch не переносит Core автоматически.

PR108 ownership, PR112 start blocks и PR113 image projection не объявляются автоматически скомпонованными этим review: parent отдельно проверяет text composition. В standalone diff PR112 helper signature/calls не меняются, но combined artifact здесь не проверен. Не утверждается полный family fix, truncated success или completed partial tools.

## Reviewed SHA256

- patch: 26c6064555f6679f6c625f94de7d1a64094a1ad5d435d07d2f35a8add147f238
- anthropic.rs: 0736a7d230ec6ab03525b5bd3ca2b47fe170a3440589d2c4f4b97a636e26e164
- errors.rs: 4a946f7256f0ac164b47c013b8ab02e6306243f79f188808dcaa6d64e28285ab
- stream.rs: 3b08830d8b892caa56064ea704ba4bd2859258d4650d20b28fbcb65da2383c2e
- tests.rs: bf7af9ca72665e20414031f602b3abf94238fa2dec7586048beda89007b141a4
- errors/stop_tests.rs: b509882a7e406b4aba2ef834c6d2f64abeca0737e883d9f66ace809f2d32f72f

Hashes пересчитаны reviewer. Rust/compiler/formatter/tests/project scripts/runtime/provider calls/install не запускались. Production, refs и публикации не менялись. Apply verification/provenance — отдельные coordinator artifacts, не runtime evidence.

## Final delta review

Повторно прочитан finalise после переноса guard: прежний dsml_filter.finish и pending-text append теперь выполняются перед context classifier, а let mut parts/drain/build Response остаются после него. Этот flush меняет только private buffer/filter state; он не yield-ит delta/completed event. Eligible failure по-прежнему не публикует partial text/tools как completed и не создаёт Response. Production outer loop останавливается на terminal Error, поэтому новый порядок private flush не меняет наблюдаемый terminal outcome. Source-level blocker не найден. Final patch/stream hashes выше независимо перепроверены. Facts о composition ещё не получены; automatic composition не заявляется. Rust/tests/runtime не запускались.

## Final composition addendum

Получен и прочитан COMPOSITION.json. Coordinator text apply/check сообщает успешные четыре порядка a–d (PR110/new/112/113) и три e–g (PR108 + explicit 110r/newr +112/113). Reviewer самостоятельно `diff -qr` подтвердил byte equality деревьев a=b=c=d и e=f=g. Это проверка текстовых артефактов, не общая сборка или runtime PASS.

Прочитана точная rebased constructor замена на baseline 108-110-base: `let mut state = AnthropicStreamState::default()` → `let mut state = AnthropicStreamState::new(status)`. Diff standalone after против after-with-PR108 содержит только три прежние ownership substitutions PR108: Arc-only import, direct mutable state, direct translate без lockguard. Eager construction, classifier и outer status gate сохраняются. errors.rs byte-identical обоим вариантам.

В combined e проверены stream additions PR112: initial_input fallback, append_text definition/calls и start_tests подключение сохранены; context guard остаётся после private DSML flush перед Response assembly. anthropic.rs совпадает с after-with-PR108; request.rs совпадает с ранее reviewed PR113 after. Новый recovery patch не поглотил start-block или image projection изменения.

Rebase patch SHA256 независимо подтверждён: `87dbfc152c5f9fbfe4d9e94220781b47aa15fd85c45842874f6624db2b83a876`. Main final patch остаётся `26c6064555f6679f6c625f94de7d1a64094a1ad5d435d07d2f35a8add147f238`. Original PR108 после 110/new ожидаемо конфликтует и это явно записано в COMPOSITION.json; автоматическая совместимость original patches не заявляется. Coordinator catalog теперь 22 sources, 10 Core blobs pin/main identical; полный catalog не перепроверялся reviewer. Verdict source acceptance не изменился. Rust/tests/runtime не запускались.
