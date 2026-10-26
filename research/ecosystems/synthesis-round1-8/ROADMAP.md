# Конкретный roadmap: существующее → недостающий seam → проверка

**Приоритет не является разрешением выполнить действие.** Ниже нет нового crate/Core rewrite/remote publication. Source-only и actual runtime нельзя объединять в «готовую систему»; [STATUS.md](STATUS.md) фиксирует слой доказательства. Все новые Rust/runtime gates остаются открытыми, пока нет подходящих ресурсов, разрешения и exact-source evidence.

## E01 — evidence.verify_spans: точная цитата из разрешённого artifact

**P1 — закрыть уже созданный consumer.** Владелец категории: tools.

**Сценарий:** Исследователь прикладывает quote/span к выводу; reviewer независимо перечитывает настроенный локальный source и проверяет точные байты.

**Уже есть:** Host-bound read_file, tool/v6, strict JSON producer и обычный ToolModuleHost callback уже есть.

**Меньшее необходимое расширение:** Pure checked-read helper + span verifier, без Core change. Настроенный source ID/path; один host-returned buffer; exact whole SHA256, UTF-8 boundaries, bounded claims. Witness сохраняет origin_verified=false и semantic_entailment=not_evaluated.

**Authority / ownership:** Host владеет read authority и callback; модуль только проверяет возвращённые bytes. Neutral helper не исполняет FS и не импортирует чужую module implementation.

**Текущий статус:** Source-ready R11;39 authored Rust cases uncompiled/unrun. Offline lock/metadata/fmt и source/23 Python packaging controls не заменяют runtime. Remote package отсутствует.

**Следующая причинная проверка:**
- 39 точных Rust cases и positive/negative own-wire demonstration против неизменных source hashes.
- Отдельно actual Core + выбранный registered reader: wrong path/call, truncation/redaction, UTF8 split, stale hash, cancellation и output cap.
- Не считать host AfterTool transformation доказательством исходных disk bytes или freshness.

Источник решения: [Round 2](SOURCE-ARTIFACTS.md#round-2), [Round 3](SOURCE-ARTIFACTS.md#round-3), [Round 4](SOURCE-ARTIFACTS.md#round-4), [Round 5](SOURCE-ARTIFACTS.md#round-5); группы CX-2, RC-1 в [карте](MECHANISMS.md).

## E02 — Correction memory: witness → proposal → conditional write

**P1 — исправить compatibility и затем проверить storage.** Владелец категории: memory.

**Сценарий:** Исправить устаревший локальный факт только если source quote проверена и target revision не изменилась; повтор operation ID возвращает прежний durable outcome, не выполняя новую запись.

**Уже есть:** Existing memory-pack read/append и evidence blocks selection не делают replace/retract CAS; Core checkpoints CAS относится к workflow history, не arbitrary memory DB.

**Меньшее необходимое расширение:** Реальный configured SQLite store, expected-revision conditional update и отдельный exact-payload idempotency outcome. Consumer повторно вызывает зарегистрированный verifier, не принимает model-supplied receipt; свежая проверка до transaction, replay outcome явно исторический.

**Authority / ownership:** Host authority отдельно от database transaction; module store owner задаёт path/config/store identity. Никакой общей memory authority, hidden session read или magic host CAS.

**Текущий статус:** Исторический R17:58 source-reviewed cases unrun, затем выявлена source-only valid raw-argument incompatibility. Отдельная raw-compat candidate69 cases authored, independent source review accepted; runtime pending; всё uncompiled/unrun, lock blocked missing rusqlite. Pairing4 и 3 wire-file cases (2 own-binary restart/cancellation +1pure framing helper) входят в58; все uncompiled/unrun.

**Следующая причинная проверка:**
- Исполнить accepted raw-compat revision с SDK normalization-order negatives; не оживлять frozen R17 молчаливой правкой.
- Реальная SQLite conflict race, same-ID same-payload replay, changed payload rejection, response-loss after commit, store/config relocation mismatch и rollback/error cases.
- Actual-module verifier pairing и restart fixtures отдельно от будущей Core approval/journal/official-reader интеграции.

Источник решения: [Round 2](SOURCE-ARTIFACTS.md#round-2), [Round 3](SOURCE-ARTIFACTS.md#round-3), [Round 4](SOURCE-ARTIFACTS.md#round-4), [Round 6](SOURCE-ARTIFACTS.md#round-6); группы MM-1, MM-2, AP-1 в [карте](MECHANISMS.md).

## E03 — SessionUsageSnapshot summary

**P1 — лёгкий read-only consumer, runtime ещё открыт.** Владелец категории: observability.

**Сценарий:** Оператор видит, сколько записанных Direct/Auxiliary exchanges имеют известные tokens, а где usage отсутствует; сравнивает запросившиеся модели и statuses.

**Уже есть:** SessionUsageSnapshot и AppServer/stdio consumers уже существуют. Не требуется новый usage collector или journal.

**Меньшее необходимое расширение:** Pure typed projection существующего snapshot: group by observed origin/requested model/status; checked sums; optional missing denominators — все exchanges группы; unavailable отличается от пустого snapshot.

**Authority / ownership:** Caller выбирает/экспортирует snapshot. Summarizer не имеет FS/network/tool authority, не читает hidden session paths.

**Текущий статус:** R18 source-ready37 authored Rust cases uncompiled/unrun; offline lock/metadata/fmt passed. Static fixture arithmetic отдельно проверена:7 exchanges/6groups/1380known tokens, не Rust execution.

**Следующая причинная проверка:**
- 37 exact tests, reachable2MiB/+1 output cap, duplicate/exchange consistency, overflow, optional missingness и unavailable-versus-empty.
- Собственный stdin example под outer deadline; это не actual AppServer transport.
- Owner, provider attempts/retry lineage/serving model/currency cost оставить unavailable, не выводить из текста.

Источник решения: [Round 5](SOURCE-ARTIFACTS.md#round-5), [Round 6](SOURCE-ARTIFACTS.md#round-6); группы OB-1 в [карте](MECHANISMS.md).

## E04 — Read-only recovery inspector

**P2 — сначала host-side interface и fixtures.** Владелец категории: recovery.

**Сценарий:** После прерывания показать effect recorded, final result recorded, checkpoint/interruption и unknown categories, чтобы оператор не повторил действие вслепую.

**Уже есть:** Validated JournalProjection уже хранит records и interruption sets; eval/replay имеют реальные consumers. ConversationView намеренно уже по содержанию, чем полный journal.

**Меньшее необходимое расширение:** App/host-side projection поверх разрешённой session/revision boundary. Для effect-without-final-result читать record phases, а не только unresolved_tool_calls.

**Authority / ownership:** Existing host/app reader выбирает scope и redaction; внешнему tool module не даётся direct access к session directory.

**Текущий статус:** Только source-grounded proposal; reader authorization/export и UI consumer не реализованы. Не новый ledger и не resume grant.

**Следующая причинная проверка:**
- Producer-shaped fixtures: effect без final result, rejected call, canceled with settled effect, corrupt owner/sequence, stale revision.
- Отчёт не запускает инструменты; отсутствующая запись остаётся unknown, а не no-effect.
- Отдельно проверять actual authorized export и exact schema/pin, прежде чем называть Core integration.

Источник решения: [Round 3](SOURCE-ARTIFACTS.md#round-3), [Round 4](SOURCE-ARTIFACTS.md#round-4), [Round 6](SOURCE-ARTIFACTS.md#round-6), [Round 8](SOURCE-ARTIFACTS.md#round-8); группы RC-1, RC-2 в [карте](MECHANISMS.md).

## E05 — Два независимых reader → source reviewer → решение

**P2 — composition, не новая crate.** Владелец категории: planning.

**Сценарий:** Проверить research claim: один reader восстанавливает producer chain, второй failure/consumer chain; reviewer заново читает источник.

**Уже есть:** Configured child profiles, task/collaboration, parallel_safe limits и plan_execute_review уже есть. Последняя безtools review-фаза не заменяет независимое чтение.

**Меньшее необходимое расширение:** Operator-defined read-only profiles и договорённость вывода supported/contradicted/not_checked, связанная с source pin/span. Не новый enforced DTO и не majority vote.

**Authority / ownership:** Host владеет child admission/tool policy; оператор — allowed artifacts/configs. Tool allowlist не filesystem sandbox, parallel_safe — декларация.

**Текущий статус:** Round7 COMPOSITION.md — design-only, TOML syntax checked, runtime integration не выполнена. Pi actual validated readiness остаётся advisory и доверяет supplied statuses.

**Следующая причинная проверка:**
- Профили не могут расширить tool surface через prompt/summary; reviewer реально перечитывает permitted artifact.
- Lifecycle completed≠goal accepted; queued/parked/timeout/canceled/truncated summary имеют отдельные outcomes.
- No retained peer → новый ограниченный read task, не обещание durable восстановления команды.

Источник решения: [Round 1](SOURCE-ARTIFACTS.md#round-1), [Round 2](SOURCE-ARTIFACTS.md#round-2), [Round 7](SOURCE-ARTIFACTS.md#round-7); группы PL-1, PL-2, AP-2 в [карте](MECHANISMS.md).

## E06 — Route/fallback/context consistency corpus

**P2 — corpus до нового router.** Владелец категории: context.

**Сценарий:** Сменить модель после overflow/failure, не потеряв инструментальные факты, output schema и terminal cancellation.

**Уже есть:** BeforeModel request rebinding/shape/tool validation; context preparation/compaction и pair-aware recovery уже есть. Auxiliary path имеет отдельные semantics.

**Меньшее необходимое расширение:** Не новый model router по умолчанию, а authored policy corpus, фиксирующий middleware order, selected model/tool/output capabilities и допустимые failure transitions.

**Authority / ownership:** Model/workflow extensions выбирают стратегию; host повторно проверяет shape/authority. Budget owner не подменяется hook-only counter.

**Текущий статус:** Proposal only: corpus и actual pinned consumer integration ещё не написаны/не запущены. Источник показывает полезные cases, не production issue reproduction.

**Следующая причинная проверка:**
- Retry exhaustion as ordinary answer vs typed error; terminal cancel/TripWire не превращается в next provider attempt.
- Fallback to smaller context, full system/tools framing, pair crossing summary boundary, stable IDs/provenance.
- Eager tool completed before model failure сохраняется как факт; количество model nodes не выдаётся за provider attempts/currency cap.

Источник решения: [Round 5](SOURCE-ARTIFACTS.md#round-5), [Round 6](SOURCE-ARTIFACTS.md#round-6); группы CX-1, OB-1, OB-2 в [карте](MECHANISMS.md).

## E07 — Observation-bound browser recipe/driver

**P3 — только с отдельным разрешённым browser consumer.** Владелец категории: tools.

**Сценарий:** Наблюдать страницу и выполнить выбранное разрешённое действие лишь пока observation/resource generation ещё актуальны.

**Уже есть:** Dynamic tool selection, registered tools и host approval уже есть; новый browser slot Core не требуется.

**Меньшее необходимое расширение:** Реальный driver должен выдавать observation ID/epoch, resource owner, selector/action admissibility и stale rejection; recipe preview не исполняет effects.

**Authority / ownership:** App/environment owner владеет browser session; Core владеет invocation authorization. URL allowlist, approval и OS isolation различны.

**Текущий статус:** Source-only proposal; ни driver/module implementation, ни browser automation, ни end-to-end runtime не выполнены.

**Следующая причинная проверка:**
- Навигация между двумя действиями, stale selector после свежего screenshot, timeout с новым session generation.
- Denied approval → no action; rerun recipe требует новых permissions и observation, а не replay старого result.
- Resource conflict key и close ownership проверяются настоящим driver, не именем tool.

Источник решения: [Round 1](SOURCE-ARTIFACTS.md#round-1), [Round 3](SOURCE-ARTIFACTS.md#round-3); группы CX-2, TL-1, TL-2, AP-2 в [карте](MECHANISMS.md).

## E08 — App-owned committed STT → Core text → TTS

**P2 — text bridge; P3 для native realtime.** Владелец категории: media.

**Сценарий:** Прочитать вслух результат разрешённого поиска, прервать звук и перечитать ответ без повторного tool effect.

**Уже есть:** AppServer Send(text/images), message identity/completed item, active-run cancel и lag/snapshot resync уже есть.

**Меньшее необходимое расширение:** Первый seam — app playback identity/status и committed transcript. Native speech-to-speech потребует bidirectional media/floor/truncation/history contracts отдельно.

**Authority / ownership:** Приложение владеет device consent, STT/TTS/RTC resources; Core — execution/approval/history. Playback interrupt не cancel effect.

**Текущий статус:** Round8 design-only INTEGRATION-LIMITS;10 proposed gates unrun. Никаких устройств, recording, provider calls, серверов или нового crate.

**Следующая причинная проверка:**
- Queued Send не считать новым active run; Cancel ack не считать terminal settlement.
- Late interrupt старого поколения не останавливает новый ответ; completed item не terminal turn и не heard acknowledgement.
- Reconnect не читает snapshot вслух автоматически; partial/unknown delivery не повторяет effectful tool; close освобождает own media resources.

Источник решения: [Round 8](SOURCE-ARTIFACTS.md#round-8); группы MD-1, MD-2, TL-2 в [карте](MECHANISMS.md).

## E09 — Durable review inbox

**P3 — новый backend contract только при реальной долгой задаче.** Владелец категории: approval.

**Сценарий:** Correction proposal ждёт reviewer вне текущего turn/process, затем применяется только к исходной версии/операции после новой host проверки.

**Уже есть:** Bounded in-turn Ask и same-root WorkflowContinuation уже есть; это не durable suspended task с persisted approver identity.

**Меньшее необходимое расширение:** Authenticated decision + versioned pending proposal, expiry/cancel, transactional claim/attempt ownership, actual backend idempotency и reconciliation.

**Authority / ownership:** Host/backend владеет approval/resume authority. Module/model supplied bool или receipt hash не создаёт разрешение.

**Текущий статус:** Proposal only; store/consumer/authentication/restart protocol не реализованы. До появления потребности предпочтительнее bounded approval/read-only report.

**Следующая причинная проверка:**
- Stale/expired/canceled decision, modified payload/revision, duplicate claim, crash around decision/write boundary.
- Restart повторно связывает pending identity, current authority и target revision; no automatic repeat по отсутствию final text.
- Actual backend crash/concurrency evidence, не DTO serialization tests.

Источник решения: [Round 1](SOURCE-ARTIFACTS.md#round-1), [Round 4](SOURCE-ARTIFACTS.md#round-4); группы AP-1, RC-2, MM-2 в [карте](MECHANISMS.md).

## E10 — Owner-aware read-only journal export

**P3 — только если narrow snapshot недостаточен.** Владелец категории: observability.

**Сценарий:** Оператор хочет связать known usage конкретного tool/context/workflow с origin и owner, не угадывая по transcript.

**Уже есть:** Journal ModelRequest/Response facts содержат больше attribution, чем SessionUsageSnapshot; validated projection/eval reader уже есть.

**Меньшее необходимое расширение:** Host/app-authorized bounded export с revision/record boundary и explicit missing fields. Provider attempt lineage требует отдельного реального adapter producer; валютная оценка — operator-versioned price input.

**Authority / ownership:** Host export owner читает existing facts; parser/summarizer не получает hidden session FS. Pricing и budget enforcement не выводятся из отчёта.

**Текущий статус:** Отдельное proposal, не minimum contract R18. Не новый ledger/универсальный budget hook и не обещание полной billing attribution.

**Следующая причинная проверка:**
- Known owner vs absent, Direct/Auxiliary, partial usage, failed/unfinished exchange, invalid cross-owner linkage.
- Не называть exchange count попытками provider; unknown serving model/retries остаются unknown.
- Любая future currency estimate маркируется estimated с price version; measured provider counters отдельно. Reserve/settle quota требует другого consumer/контракта.

Источник решения: [Round 5](SOURCE-ARTIFACTS.md#round-5), [Round 6](SOURCE-ARTIFACTS.md#round-6); группы OB-1 в [карте](MECHANISMS.md).

