# Карта механизмов по владельцу и consumer

Это **16 рабочих групп**, а не новый счётчик независимых находок или дефектов. Дедуплицирована общая задача, но различия реализации сохранены. Каждый источник остаётся pinned source-only с исходным read coverage; [INPUTS.json](INPUTS.json) связывает отчёты/ledgers/hash/pins. Runtime-примеры и prototypes отделены в [STATUS.md](STATUS.md).

## PL-1 · planning — План-предложение не является исполнительным scheduler

**Кто потребляет / владеет:** Координатор/workflow решает, какой узел запускать; host отвечает за admission каждого вызова.

**Общее и различия:** Pi readiness, ADK graph и AgentScope team используют зависимости/переходы, но Pi лишь вычисляет frontier из supplied statuses; ADK resume привязан к durable event/state identity; AgentScope делегирует через реальные tool/task loops.

**Уже есть в Proteus:** planning.ready_steps; workflow/v20; context/model/tools/events/checkpoints; bounded task/collaboration.

**Минимальная недостающая часть:** Не ещё один DAG DTO: нужен consumer фактов выполнения, если план должен автоматически запускать работу. Для первого source-review сценария достаточно существующих child profiles.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-A01, ECO-A06, ECO-X01; [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-01, ECO7-02, ECO7-14. Roadmap: E05.

## PL-2 · planning — Транспортное завершение, budget stop и достижение цели различны

**Кто потребляет / владеет:** Workflow/координатор владеет acceptance; child control plane владеет lifecycle.

**Общее и различия:** AgentScope может отображать max-iteration outcome как transport success, тогда как GoalPipeline имеет отдельный verifier verdict. LiveKit speech done имеет ещё более узкий смысл; он не заверяет tool/goal.

**Уже есть в Proteus:** Child lifecycle metadata; existing review workflow; Hermes gates с явно выбранной receipt generation.

**Минимальная недостающая часть:** В output/UI разделить completed/canceled/partial и supported/not_checked. Проверяющий должен перечитать источник, не голосовать по summary.

Основание: [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-03, ECO7-04, ECO7-10, ECO7-13; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R06. Roadmap: E05.

## CX-1 · context — Model-view преобразование не равно canonical history mutation

**Кто потребляет / владеет:** Context/compaction extension предлагает projection; host принимает identity/revision/checkpoint.

**Общее и различия:** Browser summary, ADK state events, DeepAgents summary events, LangChain state replacement и Mastra outbound prompt pruning решают близкую задачу, но меняют разные хранилища. Tool pairing сохраняет protocol shape, не outcome внешнего действия.

**Уже есть в Proteus:** ConversationSnapshot/View, context preparation, canonical part/message identity, target revision/checkpoint, pair-aware recovery Modules.

**Минимальная недостающая часть:** Не дублировать compactor: нужен корпус composition cases с полным выбранным request, сохранением call/result facts и явной provenance при replacement.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-B07, ECO-A09; [Round 2](SOURCE-ARTIFACTS.md#round-2) — ECO2-P01; [Round 5](SOURCE-ARTIFACTS.md#round-5) — ECO5-C01, ECO5-C02, ECO5-C03, ECO5-C06; [Round 6](SOURCE-ARTIFACTS.md#round-6) — ECO6-C01, ECO6-C02. Roadmap: E06.

## CX-2 · context — Ссылка и свежий preview не являются проверенным источником

**Кто потребляет / владеет:** Reader/driver производит наблюдение; consumer проверяет completeness и версию именно этого наблюдения.

**Общее и различия:** BrowserUse связывает действие с observation, OpenHands отдельно живёт browser session/selector; offload в DeepAgents может вести к позже изменённому файлу. Exact quote witness проверяет другой контракт: конкретный host-returned buffer.

**Уже есть в Proteus:** Host-bound read_file, existing checked JSON producer; динамический narrow-only tool selection.

**Минимальная недостающая часть:** Для цитаты — exact source/config/digest/UTF8 span. Для браузера — отдельные observation epoch/resource identity и повторная проверка action, не один общий receipt.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-B01, ECO-B02; [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-10, ECO3-11, ECO3-12; [Round 5](SOURCE-ARTIFACTS.md#round-5) — ECO5-C04, ECO5-C05. Roadmap: E01, E07.

## MM-1 · memory — Выбор памяти, её изменение и попадание в prompt различны

**Кто потребляет / владеет:** Context provider выбирает видимые facts; mutable backend хранит версии; prompt consumer обновляет projection.

**Общее и различия:** Letta V1 attach/detach меняет membership; Letta Code worktree/commit/sync/prompt имеют разные outcomes; Strands extraction accepted/stored/flush и session snapshot не совпадают. Исторический V1 не описывает текущий Letta Code.

**Уже есть в Proteus:** memory-pack append/recall + read-only provider; letta.evidence_blocks supplied revision/scope/tombstone selection; ConversationView.

**Минимальная недостающая часть:** Нужен correction consumer, не ещё один selector. Скрытие блока не обещает удаление всех копий; первая correction версия отдельно задаёт, есть ли retract/delete.

Основание: [Round 2](SOURCE-ARTIFACTS.md#round-2) — ECO2-L01, ECO2-L02, ECO2-L03, ECO2-L04, ECO2-L05, ECO2-S01, ECO2-S03, ECO2-P02. Roadmap: E02.

## MM-2 · memory — CAS и идемпотентность принадлежат настоящему backend

**Кто потребляет / владеет:** Storage owner атомарно связывает expected revision, exact payload, operation ID и результат.

**Общее и различия:** Letta worker ownership/generation защищает cleanup; Mastra queue timeout не storage fence, а compatibility method с applied=true не равен проверенному conditional update. Pydantic snapshot identity/retention и transaction отличаются по store.

**Уже есть в Proteus:** Core checkpoint CAS не является CAS произвольной пользовательской памяти. Host approval не заменяет SQLite transaction; witness не даёт write grant.

**Минимальная недостающая часть:** Существующий authored correction-memory должен проверить реальный conditional write + stable replay и rejected changed payload; source-only runtime gate ещё открыт.

Основание: [Round 2](SOURCE-ARTIFACTS.md#round-2) — ECO2-L06, ECO2-L07, ECO2-L08; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY06, PY07; [Round 6](SOURCE-ARTIFACTS.md#round-6) — ECO6-M01, ECO6-M02, ECO6-M03. Roadmap: E02.

## TL-1 · tools — Каталог доступных инструментов — scoped view, не полномочие

**Кто потребляет / владеет:** Host registry/policy владеют callable surface; workflow может лишь сузить/выбрать разрешённое.

**Общее и различия:** Browser URL-dependent schema, ADK invocation cache и OpenHands MCP reconciliation имеют разные freshness scopes. Discovery успешен не значит, что tool approved или его session жива.

**Уже есть в Proteus:** BeforeToolSelection narrow-only contract; dynamic selection; registered tool specs; policy visibility; portable catalog/load example.

**Минимальная недостающая часть:** Для конкретного browser/remote resource consumer нужны epoch/version и stale refusal. Не строить ещё один глобальный registry, не выводить tool grants из skill metadata.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-B01, ECO-A07; [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-14; [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-06. Roadmap: E07.

## TL-2 · tools — Ресурс и lease живут не столько же, сколько отдельный tool call

**Кто потребляет / владеет:** Environment/session/worker owner владеет resource release; invocation owner владеет данным вызовом.

**Общее и различия:** OpenHands permit удерживается цепочкой работ, resource_key задаёт конфликт; Pydantic размещение worker меняет toolset lifetime; LiveKit session AsyncToolset переживает handoff, activity tools закрываются иначе.

**Уже есть в Proteus:** BoundTools invocation-bound callback/cancellation; configured process peers и existing child limits. Это не автоматически session-long detached service.

**Минимальная недостающая часть:** Если нужен долгий сервис, сначала задать ownership/close/reconcile и запрет поздних callback после завершённого invocation. Не выдавать session lifetime как универсальную опцию обычного tool.

Основание: [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-05, ECO3-07, ECO3-09, ECO3-13; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY10; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R09, R8-R13, R8-R14. Roadmap: E07, E08.

## AP-1 · approval — Решение связано с конкретным вызовом и версией, не со словом approved

**Кто потребляет / владеет:** Core/host approval channel авторизует действие; resume consumer повторно связывает pending identity/args.

**Общее и различия:** ADK confirmation привязан к исходному call; Pydantic deferred decision требует resume validation/backend; OpenHands повтор run может быть SDK approval convention. Это разные механизмы, не взаимозаменяемый bool.

**Уже есть в Proteus:** Allow/Ask/Deny, origin/owner, schema/hooks, durable resolution, invocation-bound host; same-root continuation отдельно от suspended durable task.

**Минимальная недостающая часть:** Для долгого review нужен version-bound pending record и authenticated decision store; до этого bounded in-turn approval, без model-supplied grants.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-A04; [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-02; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY01, PY02, PY03, PY08, PY09. Roadmap: E09.

## AP-2 · approval — Роль, navigation allowlist и duplicate confirm не являются security boundary

**Кто потребляет / владеет:** Оператор/host конфигурирует tool/process/file authority; модель предлагает содержимое задачи.

**Общее и различия:** Browser navigation policy ограничивает URL, не все эффекты; AgentScope verifier role может иметь write-capable tools; LiveKit confirm_duplicate читается из tool args и управляет in-flight duplicate, не независимым human approval.

**Уже есть в Proteus:** Tool allowlist и host policy; explicit child profiles; ReadOnly классификация не filesystem sandbox.

**Минимальная недостающая часть:** Настроить настоящие restrictions в композиции и проверять отсутствие расширения полномочий через summary/skill/memory. Не обещать изоляцию по имени роли.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-B06; [Round 2](SOURCE-ARTIFACTS.md#round-2) — ECO2-L09; [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-05, ECO7-06, ECO7-13; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R10. Roadmap: E05, E07, E08.

## RC-1 · recovery — Repair/notification/result/effect — разные наблюдаемые факты

**Кто потребляет / владеет:** Host journal сохраняет resolution/effect/result; UI и transcript adapters показывают только свои проекции.

**Общее и различия:** ADK/OpenHands/DeepAgents чинят dangling call pairing; Mastra переносит eager tool outcomes после model failure; Pydantic различает effect frontier/checkpoint; LiveKit сохраняет tool result до spoken notification.

**Уже есть в Proteus:** ToolEffectRecorded отдельно от ToolResultRecorded; validated JournalProjection, eval/replay consumers. unresolved_tool_calls не включает effect-without-final-result.

**Минимальная недостающая часть:** Read-only forensic projection должна читать existing records и показывать missing final/unknown отдельно. Не добавлять второй ledger или автоматический retry по отсутствию текста.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-A05, ECO-A09; [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-01, ECO3-08; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY04, PY05, PY14; [Round 5](SOURCE-ARTIFACTS.md#round-5) — ECO5-C02; [Round 6](SOURCE-ARTIFACTS.md#round-6) — ECO6-R03; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R08, R8-R15. Roadmap: E04.

## RC-2 · recovery — Replay, resume, reconnect и rerun имеют разные эффекты

**Кто потребляет / владеет:** Orchestrator/backend выбирает допустимый recovery; transport owner восстанавливает соединение, не бизнес-действие.

**Общее и различия:** Browser history/rerun_actions повторяют реальные действия; ADK fast-forward и Temporal replay зависят от stable identity; AgentScope saved AgentState не сохраняет автоматически pipeline instance counters; LiveKit reconnect replay-ит provider mirror, не durable tool ledger.

**Уже есть в Proteus:** Canonical offline replay; existing turn/child continuation; journal validation. Они не восстанавливают любой внешний environment и не дают repeat authority.

**Минимальная недостающая часть:** Сначала inspector и явный operator decision. Durable review/backend только при конкретном межпроцессном ожидании и реальных transactional semantics.

Основание: [Round 1](SOURCE-ARTIFACTS.md#round-1) — ECO-B03, ECO-A06; [Round 2](SOURCE-ARTIFACTS.md#round-2) — ECO2-S04, ECO2-S06; [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-15; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY08, PY13; [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-10, ECO7-11, ECO7-15; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R12. Roadmap: E04, E09.

## MD-1 · media — Остановить звук, модель и внешний эффект — три команды

**Кто потребляет / владеет:** App media owner владеет playback; model adapter — generation; Core — execution lifecycle.

**Общее и различия:** LiveKit имеет full/partial/skipped sink result, generation-bound session cancel и отдельные ToolCallEnded/ToolReplyUpdated. Без alignment partial transcript может оставаться полным text buffer; queue position не acoustic receipt.

**Уже есть в Proteus:** AppServer text/images Send, completed item IDs, cancel active run, lag/snapshot resync; no audio/video-frame variant в выбранном ContentPart.

**Минимальная недостающая часть:** Небольшая STT/text/TTS оболочка может сохранить границы; native speech-to-speech и authoritative heard context требуют новых contracts.

Основание: [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R01, R8-R04, R8-R05, R8-R06, R8-R08, R8-R16, R8-R17, R8-R18. Roadmap: E08.

## MD-2 · media — Speculation и floor control нельзя незаметно перенести в effectful workflow

**Кто потребляет / владеет:** Conversation/media scheduler решает, когда подготовленный ответ получает право стать слышимым; host отдельно admits tools.

**Общее и различия:** LiveKit может заранее генерировать LLM/TTS и переиспользовать candidate при эквивалентных context/tools, но tools запускаются после floor gates. False interruption может pause/resume без отмены generation; session capability влияет на reuse/truncate.

**Уже есть в Proteus:** WorkflowHost accepted preparation/operation gate, закрытие stream перед compaction; отдельной native media floor semantics нет.

**Минимальная недостающая часть:** Первый bridge только committed transcript. Спекулятивные effect-free branches и remote context truncation — отдельное последующее design, не обещанный speedup.

Основание: [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R02, R8-R03, R8-R07, R8-R13, R8-R15. Roadmap: E08.

## OB-1 · observability — Usage counters, attempts и стоимость имеют разных producers

**Кто потребляет / владеет:** Core usage projection экспортирует записанные exchanges; provider adapter знает retries; pricing owner задаёт versioned rates.

**Общее и различия:** LangChain model-node limit не считает каждый handler attempt; Mastra observer/processor retries имеют свои caps, cost limiter retrospective; LiveKit media/auxiliary paths также не равны пользовательским репликам.

**Уже есть в Proteus:** SessionUsageSnapshot: Direct/Auxiliary, requested model,status,observed token counters; journal records богаче, но snapshot не содержит owner/attempt lineage/cost.

**Минимальная недостающая часть:** Переиспользовать pure snapshot summarizer. Owner-aware exporter — отдельный host/app consumer; unknown сохранять, не восстанавливать по тексту или числу steps.

Основание: [Round 5](SOURCE-ARTIFACTS.md#round-5) — ECO5-B01, ECO5-B02, ECO5-O02, ECO5-R01; [Round 6](SOURCE-ARTIFACTS.md#round-6) — ECO6-M05, ECO6-B01, ECO6-B02, ECO6-B03. Roadmap: E03, E10.

## OB-2 · observability — Измеренный слой и предел утверждения должны совпадать

**Кто потребляет / владеет:** Оператор сравнивает bounded evidence; validator проверяет именно заявленный interface.

**Общее и различия:** Source parallelism не measured speedup; SDK wire pass не Core admission; queue timer не hard preemption; model success не user acceptance. Read coverage/fetched count и heterogeneous runtime controls не складываются в один score.

**Уже есть в Proteus:** Отдельные source pins, scoped Core21 checks, strict standalone tests, actual Pi/Letta binary supplements и source-only R11/R18/R17.

**Минимальная недостающая часть:** В roadmap у каждой строки должны быть свой gate и статус; price/performance/resume/security claims требуют собственных consumers и causal controls.

Основание: [Round 3](SOURCE-ARTIFACTS.md#round-3) — ECO3-16; [Round 4](SOURCE-ARTIFACTS.md#round-4) — PY11, PY12; [Round 5](SOURCE-ARTIFACTS.md#round-5) — ECO5-F03; [Round 6](SOURCE-ARTIFACTS.md#round-6) — ECO6-R04; [Round 7](SOURCE-ARTIFACTS.md#round-7) — ECO7-04; [Round 8](SOURCE-ARTIFACTS.md#round-8) — R8-R06. Roadmap: E01, E02, E03, E06.

