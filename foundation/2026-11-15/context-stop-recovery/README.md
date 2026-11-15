# Context-stop: recovery-only source candidate

## Результат и статус

Подготовлен **source-only candidate для уже известного context-stop из PR85**, не новая finding. Он сохраняет actionable причину успешной HTTP200 генерации, оборванной заполнением context window, вместо её последующего превращения в generic Length/Other. Существующий compactor получает ContextWindowExceeded и может сокращать history, а не повторять тот же oversized summary request.

**Это не полный outcome/accounting fix. Usage неуспешной генерации по-прежнему не сохраняется в durable usage projection.** Rust, compiler, formatter, tests, fixtures, приложение и live provider не запускались. Независимое exact source review не нашло blocker, но это не compile/runtime PASS и не готовность production.

## Версии и зависимости

Свежие refs проверены в начале и конце:
- Modules: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules actual Core pin: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery main: `8977b4c31b11f03cb03c7207ca92fb64cb6c0297`, включая PR116.

**Patch зависит от PR110**, который вводит provider-local errors.rs и определённый HTTP/SSE status handling. Он не предназначен для clean upstream apply:
1. `context-stop-recovery-on-PR110.patch` применяется к Modules c035 + standalone PR110.
2. `context-stop-recovery-on-PR108-PR110.patch` применяется к Modules c035 + PR108 + уже проверенный текстом `anthropic-failure-on-PR108.patch` из PR110.

**PR111 нужен отдельно для inherited direct Rust Model::complete**, чтобы canonical stream Error не терялся в старом default fold. Его публикация не меняет actual Modules dependency pin. Для этого scope потребуются осмысленное обновление зависимости и пересборка consumers; здесь pin/lockfiles не меняются. Уже корректные stock ModelService/BoundModel/process terminal paths и nonstream startup Err не зависят от исправления default fold для самого сохранения kind.

PR112/113 не обязательны для новой classification; ниже проверена только текстовая композиция с ними. Все названные PR остаются отдельными uncompiled proposals, не установленными upstream исправлениями.

## Точный контракт candidate

| Native input | Результат |
|---|---|
| HTTP200 и точный model_context_window_exceeded после успешного decoding / terminal SSE message_stop | Existing ModelFailureKind::ContextWindowExceeded |
| max_tokens на любом status | Прежняя Length projection |
| Missing/unknown stop reason | Прежняя Unknown projection |
| Иной admitted HTTP status с model_context_window_exceeded | Прежняя Response/Length форма, не новый Error |
| Existing malformed JSON, provider error envelope, decoder failure | Прежняя error precedence |
| Обычный end_turn, stop_sequence, tool_use | Прежняя successful projection |

Provider-specific stop классифицируется только в native adapter. Core validators, shared DTO, process schema, compactor recovery, retry budgets и backoff не меняются. Нет проверки provider text в workflow, новых retry loops или framework.

[Первичная документация Anthropic](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) различает заполнение context window и исчерпание заданного output cap. Context-window stop означает усечённую генерацию, а не полноценный завершённый ответ. Документация проверена 2026-11-15.

## Изменения

- В существующем errors.rs один небольшой private classifier проверяет HTTP200 и точный stop reason. Он создаёт existing typed failure с empty completed_messages.
- Nonstream client сначала выполняет прежние HTTP checks и decoder. Только после успешного decoding выбирает recovery по сохранённому provider_metadata.stop_reason. Сам status-blind decoder API остаётся прежним, включая его error precedence и использование в PR112 tests.
- StreamState получает actual HTTP status через private new(status). State и message id создаются eager до generator, как раньше, в обеих ownership версиях.
- На finalise сохраняется прежний private DSML flush, затем eligible context stop отдаёт terminal Error до построения Response. Partial deltas могли уже быть показаны, но buffer не превращается в completed message или executable tool calls.
- PR110 outer status gate остаётся. Одного этого gate недостаточно: unconditional новый Error с пониженным kind всё равно изменил бы прежний non-200 Response shape. Поэтому eligibility проверяется до выбора terminal shape.

Existing stream и прежде не разбирал tool args, когда stop не tool_use. Candidate не объявляет дополнительное исправление malformed tool JSON; настоящий tool_use с malformed args по-прежнему получает Other.

В production добавлено 38 строк, ещё 3 строки подключения нового test module. Это не LOC-оптимизация: устраняется потеря semantic cause, используя уже существующую recovery abstraction. Нет заявленного RAM/latency/throughput выигрыша.

## Usage gap и видимые изменения

В validated stock path прежний Length отклоняется прежде model_response_recorded. Error outcome несёт ModelFailure без usage; UsageProjection берёт counters только из Response. Просто emitted Usage event также не стал бы durable: текущий recorder сохраняет из stream только MessageCompleted.

Candidate **оставляет этот gap**, а не решает accounting. Дополнительные recovery attempts могут содержать generated usage, не отражённый в прежней error projection. Нельзя обещать полную стоимость, уменьшение оплаченных токенов или полноту usage_summary.

Для direct raw native consumer, который прежде принимал Length Response с usage без validation, HTTP200 context stop теперь становится typed failure. Поэтому утверждение «usage/projection не меняется нигде» было бы неверным. Это намеренное изменение terminal outcome выбранного recovery-only scope; failure carrier не сохраняет прежний raw response.

Partial text, incomplete tools и provider usage не помещаются в completed_messages ради обхода этого ограничения. Полное outcome/accounting исправление остаётся на отдельном HOLD до выбора и проверки durable contract.

## Предложенные тесты, все NOT RUN

В новом errors/stop_tests.rs четыре pure test functions:
1. Матрица exact status/stop eligibility, empty completed_messages, typed anyhow context и serde round trip.
2. HTTP200 context stop после partial text и incomplete tool JSON: только terminal Error, без Response, MessageCompleted или ToolCallFinished.
3. Другие status/stop сохраняют прежние Response/finish reason/usage; normal tool_use работает по прежнему decoder, malformed tool_use остаётся Other.
4. Nonstream decoder сохраняет error precedence и metadata, из которой выбирается exact classification.

Обновлён один existing context-stop test, ранее требовавший Length от stream. Nonstream checks проверяют композицию decoder+classifier, но не исполняют async HTTP client. Stream checks проверяют accumulator, не реальный HTTP driver. Нет выполненного compactor retry, Core dependency или usage integration run.

При доступном разрешённом toolchain нужны focused model-pack tests и exact HTTP loopback matrix обоих modes, включая non-200 controls; затем compactor trim-and-retry с successful-summary/max_tokens controls и отдельная accounting проверка. Старые test results из PR85 не подтверждают этот patch.

## Source и текстовая композиция

- 22 baseline source blobs сверены с repository Git SHA; десять relevant Core blobs совпадают main/actual pin.
- Main patch прошёл только `git apply --check --whitespace=error` и текстовое применение; resulting bytes совпали с after/.
- Четыре порядка PR110/new/PR112/PR113 дают одинаковые final bytes.
- Три порядка PR108 + reviewed PR110-on-PR108 + rebased new + PR112/PR113 также дают одинаковые final bytes.
- Исходный PR108 после PR110/new по-прежнему конфликтует. Это не скрыто: для combined path предоставлен отдельный rebase, не заявление произвольного auto-merge.
- First draft guard перед DSML flush пересекался с PR112 append_text hunk. Тот же guard перенесён после private flush и повторно независимо прочитан. Это исправление текстовой композиции; runtime результата не заявляется.
- Независимый review: `CONTEXT-STOP-RECOVERY-INDEPENDENT-REVIEW.md`.

## Артефакты

- Main patch SHA256: `26c6064555f6679f6c625f94de7d1a64094a1ad5d435d07d2f35a8add147f238`.
- Rebased patch SHA256: `87dbfc152c5f9fbfe4d9e94220781b47aa15fd85c45842874f6624db2b83a876`.
- Source identities, dependency patch identities and summarized text composition checks are included below.
- Full source snapshots, intermediate trees, raw tool logs and historical runtime logs are intentionally not published.

Upstream production refs и dependency pins не менялись. Публикация этого пакета в delivery-репозитории не применяет patch к runtime. Ничего не устанавливалось. Публиковать можно только как **непроверенный recovery-only source candidate**, сохранив зависимости и открытый accounting gap.
