# Proteus: карта механизмов и практический roadmap по Round1–8

**Главный вывод:** расширять нужно конкретные producer/consumer цепочки, а не копировать названия возможностей. В Proteus уже есть workflows, hooks, dynamic tool selection, memory/context providers, checkpoints, child control и журнал effects/results. Новые browser, memory или voice сценарии требуют явно определённой недостающей предметной границы — иногда это модуль, иногда только профиль, иногда отдельный stateful backend.

Это synthesis закреплённых source reports, не новый audit или runtime experiment. Исходные Round1–8 неизменны; исторический baseline90 не пересчитан. **16 групп ниже — редакционная группировка повторяющихся механизмов, не16 новых bugs/находок.** Точные связи с findings, pins и hashes: [mechanism-map.json](mechanism-map.json), [INPUTS.json](INPUTS.json).

Обязательные уточнения: [CAS wire-file cases:2own-binary+1helper, всёunrun](FOLLOWUP-CAS-WIRE-LAYER.md); [LiveKit reply completed — callback label, не подтверждение успешной/полной озвучки](FOLLOWUP-REPLY-STATUS.md).

## По владельцу и потребителю

| Область | Что переносимо | Что нельзя считать эквивалентным | Ближайшее действие |
|---|---|---|---|
| Planning | Readiness/frontier, bounded roles, independent reviewer | Advisory statuses, task completed и goal verified | Existing child composition E05, не ещё один planner |
| Context | Model-view projection, pair-aware boundary, progress check | Summary, canonical history, artifact snapshot и effect ledger | Route/context corpus E06; exact quote witness E01 |
| Memory | Scoped selection, progressive retrieval, version-bound correction | Attach/detach, persisted content, compiled prompt, remote sync | Проверить настоящий CAS consumer E02; selector уже есть |
| Tools | Dynamic narrowed catalogs, resource-key concurrency, owner-scoped lifetime | Tool name, live resource, current observation и permission | Observation-bound driver E07 только при реальном сценарии |
| Approval | Original-call/args/version binding, explicit host decision | Prompt-role, navigation allowlist, duplicate-confirm flag и grant | Existing host approval; durable inbox E09 только при потребности |
| Recovery | Separate effect/result/checkpoint, read-only reconciliation view | Transcript repair, diagnostic replay, reconnect и повтор эффекта | Host-side recovery inspector E04 |
| Media | Generation-bound interrupt, delivery status, explicit resource transfer | Playback stopped, model canceled и effect settled | Text STT/Core/TTS bridge E08; native realtime отдельно |
| Observability | Known/missing counters и source-bound receipts | Exchange, provider attempt, owner, price и global quota | Pure existing-snapshot consumer E03; richer export E10 отдельно |

Подробно: [MECHANISMS.md](MECHANISMS.md). Для каждого решения указаны actual owner, existing Proteus capability и семантические различия между реализациями, а не список продуктов.

## Три практических приоритета

### 1. Довести реальные consumer, а не добавить ещё crate

- **E01 evidence.verify_spans:**39 authored cases ещё unrun. Узкий смысл — совпадение SHA/UTF8 quote с host-returned buffer; не origin/entailment и не permission.
- **E02 correction-memory:** реальный SQLite conditional-write consumer уже authored. Frozen R17 имеет58unrun; отдельная raw-compat revision69unrun source-accepted после корректировки SDK normalization boundary. Нельзя называть это выполненным CAS до SQLite/pairing/restart evidence.
- **E03 usage summary:**37unrun; потребляет уже существующий SessionUsageSnapshot. Owner/attempt lineage/стоимость не присутствуют и остаются unknown; новый journal collector не нужен.

Эти проверки не запускаются автоматически этим документом. Ресурсные и разрешительные условия — отдельные, а минимальный consumer не получает новых полномочий ради удобства.

### 2. Собрать композиции из существующих возможностей

Два независимых source reader и reviewer; route/context/failure corpus; read-only recovery UI. Здесь полезнее exact fixtures и configured profiles, чем очередной универсальный agent runtime. Уже выполненные Pi, Letta и Hermes v1 direct-SDK supplements подтверждают только собственные advisory/projection/gate semantics — не историческую истинность supplied данных и не actual write→verify→stop turn.

### 3. Новую semantic boundary вводить только под отсутствующий consumer

Browser observation epoch, долгий review с restart, session-lived async tool или native audio generation требуют ownership/reconciliation. Это не причина заранее давать plugin доступ к session files, всеобщий approval bool или magic durable state. Thin text voice bridge возможен по существующему AppServer; native speech-to-speech не является transparent Model adapter.

## Что уже проверено, а что нет

[STATUS.md](STATUS.md) отдельно перечисляет:

1. Published exact-head standalone examples и ограниченные actual-Core checks.
2. Последующие independently accepted existing-binary Pi/Letta/Hermes v1 supplements — без нового Core/provenance утверждения.
3. Source-only R11/R18/correction-memory и незапущенные full-host/Core pairing gates.
4. Design-only browser/media/durable review proposals.

Результаты sibling branches не складываются в единую проверенную поставку. Исходные receipt generation v1/v2 и SDK3f/currentCore1fc не объединяются молчаливым repin. Static preflight schema2 — не запущенный module initialize.

## Антицели

- Не добавлять второй ledger или новый общий ConversationView: соответствующие Core representations уже есть.
- Не считать завершение текста/stream/handle доказательством внешнего эффекта либо его отсутствия.
- Не делать global budget hook из счётчика steps: auxiliary calls и provider attempts имеют иных producers.
- Не приписывать queue timeout/500ms cooperative grace hard preemption, rollback или descendant cleanup.
- Не выдавать exact quote/JSON assertions за истину пользовательского вывода.
- Не обещать measured speedup, full ecosystem coverage, универсальную установочную совместимость или production readiness по source inspection.

## Артефакты

- [ROADMAP.md](ROADMAP.md) / [roadmap.json](roadmap.json):10 конкретных решений, каждое со сценарием, владельцем, существующим механизмом, минимальным gap, статусом и следующим test gate.
- [MECHANISMS.md](MECHANISMS.md) / [mechanism-map.json](mechanism-map.json):16 групп в8 областях; exact source finding links.
- [PINNED-SOURCES.md](PINNED-SOURCES.md): версии и исторические различия, включая retired Letta V1 против active Letta Code.
- [ADAPTATION.md](ADAPTATION.md): происхождение этой отдельной копии и пределы её самостоятельности; исходные отчёты/receipts не включены и не объявляются опубликованными.
- Предыдущая архитектурная заметка и руководства по установке/навигации использованы как ограниченные справочные материалы, не как authority или замена exact receipts. Их hash-bound identities записаны в INPUTS; исходные файлы не изменены.

Итоговый порядок: **сначала точные producer/consumer проверки, затем композиция, только затем недостающий stateful/media contract**. Это даёт гибкость без переноса host authority в текст модели.
