# Независимый source review: canonical terminal fold

## Итог

**В exact candidate не найден source-level blocker.** Исправляется известный узкий MDC-1/PR99: inherited direct Rust Model::complete должен возвращать canonical Error как исходный typed ModelFailure. Stock ModelService/BoundModel уже корректно обрабатывали Error; новая продуктовая авария или исправление обычных workflows не заявляется.

Три реализации terminal drain сведены к одному существующему trait default без новой публичной abstraction. Source-review acceptance не означает compile/test/runtime PASS.

## Default и dispatch

- Default продолжает вызывать `self.stream(request).await?`, а не provider raw stream или service internals. После удаления overrides для ModelService/BoundModel выбирается их собственная реализация stream; сохраняются request shaping, before-model hooks, validation, recording, deadlines/cancellation и presentation ownership.
- Match возвращает Response без изменения и Error через anyhow::Error::new(failure), сохраняя весь DTO: kind, message, retry_delay_ms и completed_messages. Startup Err и outer stream Err по-прежнему проходят через `?`. Не добавляется реконструкция deltas/progress или новый retry.
- Nonterminal события игнорируются, как раньше. Голый EOF inherited helper сохраняет прежний текст `model stream ended without a complete response`. Новое поведение касается корректного terminal Error, не вымышленного Error→Response sequence.
- Async-trait/default dispatch не добавляет нового lifetime/bound: существующий Model уже Send+Sync, stream уже возвращает owned Send stream. Удалённые методы были тем же async_trait trait method, новый default не вызывает себя рекурсивно. Это статический вывод, не проверка компилятором.

## EOF invariants wrappers

- ModelService::stream остаётся неизменным и оборачивает adapter stream в validating_stream. При EOF без terminal он выдаёт прежний outer Err `model stream ended without Response event`, который новый default немедленно передаёт через event?. Поэтому новый default fallback text не становится наблюдаемым для этого wrapper path.
- BoundModel::stream_with_deadline всегда получает bound_recording_stream, который до голого EOF создаёт typed Other с тем же старым wrapper текстом и recorded completed progress. Canonical failure также дополняется progress и записывается до yield. Presentation forward-ит outer Err через event? и canonical terminal как event. Auxiliary path возвращает recording stream напрямую. Эти пути не обходят wrapper EOF machinery.
- Не меняются first terminal stop/drop semantics: default, как прежние overrides, возвращается на первом Response/Error и освобождает stream. Запись terminal происходит внутри stream до его yield.

## Imports и предложенные tests

Полный patch прочитан. После удаления production CanonicalModelResponse imports ModelService tests уже имеют собственный explicit import. В bound_model_tests.rs он добавлен явно, восстанавливая прежнюю зависимость дочерних test modules от super imports.

Четыре новых contract test functions по исходнику проверяют:

1. Все шесть текущих kinds, including retry advice, message и completed_messages через canonical Error и полный downcast/equality.
2. Response с usage сохраняется целиком после nonterminal delta.
3. Startup failure и outer typed stream Err с anyhow context сохраняются.
4. Пустой stream и только MessageCompleted заканчиваются прежним нетипизированным EOF, без превращения completed item в terminal Response.

StreamOnlyModel оставляет complete inherited. Mutex защищает одноразовый owned stream для Sync; guard не переносится через await. Test dependencies tokio macros/rt и futures-util уже присутствуют в contracts Cargo.toml. Дополнительного runtime/package install не требуется по тексту manifest; фактическая компиляция не выполнялась.

Два wrapper tests усилены: ModelService проверяет целый failure; BoundModel проверяет retry kind/advice, message и merged canonical completed progress с recorder. Fixture canonical Error завершает stream, не содержит invalid Error→Response. Новые tests не являются выполненным integration/protocol/provider доказательством. Отдельного нового dyn-Model dispatch test нет; dispatch вывод опирается на существующий trait и source.

## Scope и delivery

Core base: `bcbda4435534a296c707a1daa250813d692f68e1`. Actual Modules dependency pin `41bdfffa6e70228278b4abc758b7f81a12672f35` имеет тот же исходный contract/model.rs согласно coordinator verification; patch направлен на Core и сам по себе не обновляет pinned Modules. PR108/110 относятся к другому репозиторию. Для переноса исправления direct native adapter.complete в установленный Modules build потребуется отдельное обновление dependency/build по разрешённому workflow; здесь этого не делалось.

Полный catalog 15 blobs (включая добавленный ProcessModel source) и apply/check сообщил coordinator; reviewer самостоятельно прочитал relevant production и exact diff, а также пересчитал hashes. Rust/compiler/tests/runtime/scripts/fixtures/provider calls/install не запускались. Production, refs и публикации не менялись.

## Reviewed SHA256

- patch: `f0cec324abd93ff2e9393e19600cf30522e66564615c2477bf9edfa488883a67`
- contracts/model.rs: `b49c7d74f545961b12527be066b2905b00e7e7541a428f76e1c99d666cc57d47`
- contracts/model/tests.rs: `bf289d6ca7bc1f910060aa2ff561cc75399cad828e05b7d6396cd6464e59dbed`
- model_service.rs: `c52cf479e4b55111afe51c5471e3876e20004f4fcf547928adc4e0d4c7e8806b`
- bound_model.rs: `21a2f499bb5f79d981694aba2d5de2f0b7549550475814cc0e8bd28da34b9b5b`
- bound_model_tests.rs: `b1a9bd45b712ff41caca48a2c7e829168524e8cc913c4c41bb888bc72306acb7`
- bound_model_tests/failure_progress.rs: `c4d187f71c0893e3b0c78356354bf33cb211c666c47c43a3661cead26bfdcd9c`

## Финальный evidence addendum: ProcessModel

Независимо прочитан `impl Model for ProcessModel` и terminal участок `before/crates/proteus-core/src/process_adapters/model.rs`. Собственного `complete` override нет: direct Rust вызов использует рассматриваемый trait default. После завершения process invocation и drain очереди `guard.disarm()` выполняется до decode/count validation и terminal match. `StreamError` затем выдаёт canonical `ModelStreamEvent::Error`, а `RequestError` возвращается как typed `anyhow::Error::new(failure)`. Следовательно, новый early return default на accepted canonical terminal Error не оставляет этот CancelOnDrop guard armed. Вывод ограничен этим terminal path, не является общей проверкой cancellation или прочих branches.

Это дополнительное подтверждение raw-adapter reachability, не новый finding и не изменение verdict. Manifest 15 источников подтверждён coordinator; reviewer отдельно прочитал добавленный участок и пересчитал его SHA256: `d8bfae0798ea65d3697942669ec1c5bd729d8874f32d823f6c50c49f43b31c16`. Patch SHA256 повторно проверен и остался `f0cec324abd93ff2e9393e19600cf30522e66564615c2477bf9edfa488883a67`. After/production не менялись; Rust/runtime/tests не запускались.
