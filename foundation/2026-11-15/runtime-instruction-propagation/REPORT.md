# Runtime instructions: один локальный fix для пяти legacy sampling paths

## Статус

**Source-only patch candidate для уже опубликованного workflow-continuation P2. Не новая finding и не проверенное runtime-исправление.** В текущем Modules прежняя потеря profile instructions и причины BeforeStop имеет одну точку: legacy `request_from_state` строит список только из фиксированного System100. Исправление переносит все runtime blocks через эту точку, не добавляя ещё один prompt pipeline, trait или special case для конкретного reviewer.

Production diff: один файл `host.rs`, 466 → 470 строк, +4 net LOC. Дополнительно зарегистрирован новый test module с тремя **не запущенными** regression tests. Это исправление семейства потерь данных, а не −LOC или performance proposal.

## Точные версии и дедуп

- Modules main повторно проверен: `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Core main: `bcbda4435534a296c707a1daa250813d692f68e1`; фактический dependency pin Modules: `41bdfffa6e70228278b4abc758b7f81a12672f35`.
- Delivery main на проверке: `d83ba45ac5ac1118b1b70eaf5de308a21f093854`, последний PR108.
- Источник уже известного P2: [workflow-continuation report](https://github.com/Qweasd123tg/proteus-modules-dot/blob/d83ba45ac5ac1118b1b70eaf5de308a21f093854/research/proteus-continuous-audit-2026-11-13/evidence/workflow-continuation/REPORT.md). Его старые process/HTTP результаты не являются запуском этого patch на c0351425. Локальная копия сохранена отдельно для происхождения.
- PR106 убирает пять повторений sampling lifecycle, но сохраняет вызов того же request builder и сам P2 не исправляет. PR107 меняет JSON codec envelope, PR108 меняет model stream implementation. Они не дублируют предлагаемую правку.

## Что меняется

До: `[workflow System100]`, затем существующие intent/phase/dynamic blocks. Runtime list отсутствует.

После, в canonical vector:

1. Прежний workflow System100, с прежним текстом.
2. Все `input.runtime.instructions` в исходном порядке, с точными kind/text/priority. Никаких sort, dedup, trim или смены приоритетов.
3. Прежние условные добавления общего helper: intent Developer95, phase Developer90, dynamic-tool Developer80.

Это **порядок canonical list**, а не обещание семантического precedence у LLM. Native OpenAI и Anthropic adapters отдельно сортируют blocks по убыванию priority; их код не меняется. Порядок равных приоритетов и все исходные поля доступны адаптеру без потерь. Пустой runtime list оставляет прежний список.

Core `reviewed_workflow` уже добавляет `continuation.reason` как Developer128 перед workflow invocation. `WorkflowInvocationContext::runtime_info` передаёт этот список Modules. Поэтому patch **не читает reason отдельно** и не добавляет второй synthetic block. Это важно как для BeforeStop, так и для обычного профиля без continuation.

## Почему эта граница

Пять production sampling sites используют один legacy wrapper:

- `single_loop`: обычный запрос и forced final;
- `plan_execute_review`: plan, execute, review.

Одна правка охватывает их все, включая повторные вызовы того же site в tool loop. Циклы, private/durable history, ACK handling, tools и response validation остаются без правок. Исправленный список формируется **до** context preparation и model call, поэтому он попадает и в `ContextPreparationInput.request`, а не только в поздний payload модели.

Codex pre-turn, first sampling и subsequent sampling уже явно передают runtime blocks через другие wrappers. Общий `request_from_state_with_instruction_blocks_and_options` менять нельзя: безусловное добавление runtime list там продублировало бы Codex blocks. Candidate меняет только legacy wrapper.

Передача runtime instructions требует owned clone в новом request, как в существующем Codex path. Это необходимая доставка данных, не доказанное снижение allocation, CPU или RSS. Никакого измеримого runtime ускорения не заявляется.

## Предложенное regression coverage

Три test functions в `tests/instruction_propagation.rs`, все **NOT RUN**:

1. Exact builder list для пустого и непустого runtime; System/Developer/Project/UserPreference, одинаковый текст разных kinds, разные priorities, reason128, неизменность input.
2. Обычный profile-only invocation и root-shaped continuation fixture на всех пяти legacy sites. Проверяются число/phase запросов, exact runtime slice, отсутствие лишнего reason, присутствие тех же instructions в captured preparation request. Fake default compactor возвращает unchanged.
3. Codex first и follow-up request через `end_turn(false)`: оба списка совпадают с runtime ровно один раз, в обычном invocation и continuation.

Это предложенные Modules boundary tests, а не Core BeforeStop/HTTP интеграция. Они не проверяют successful review correction, attempt limit, fresh/warm/cold restarts, changing compaction/ACK и intent/dynamic branches. Эти ограничения не скрыты за историческим runtime report.

## Что действительно проверено сейчас

- 21 сохранённый source file совпал с Git blob SHA; Git blob SHA перечислены в `SOURCES.json`; SHA256 итоговых изменённых файлов записаны в `PATCH-VERIFICATION.json`.
- Независимо прочитаны exact production diff, fixture/control-flow и pinned contracts. Итог в `INSTRUCTION-PROPAGATION-REVIEW.md`; source-level blockers не найдены. Это не compile approval.
- `git apply --check --whitespace=error` и применение как текста в изолированных копиях прошли для всех шести порядков трёх patches: этого, PR106 и PR107. Итоговые Rust bytes равны во всех порядках. Evidence в `PATCH-VERIFICATION.json`. Это проверка совместимости текста, **не build или тест совместной версии**.
- Rust, cargo, compiler, rustfmt, clippy, project scripts, tests, fixtures, providers и приложение не запускались; toolchain/dependencies не устанавливались. Production checkout и upstream refs не изменялись, публикаций этим проходом нет.

## До интеграции

Нужны разрешённый toolchain, компиляция `coding-workflow`, focused regression tests и применимый module/contract gate через штатный runner. Затем стоит повторить историческую BeforeStop/profile wire-матрицу на exact patched binary, включая Codex no-dup control. Пока этого нет, публиковать только как непроверенный source candidate, не как готовое исправление или прошедшие tests.

## Пакет публикации

Patch, итоговый source review, source manifest и результаты текстового применения. Raw logs, локальные source snapshots, исторический report и устаревший INDEPENDENT-REVIEW не публикуются. SOURCES.json перечисляет исходные файлы и blob SHA, не вложенные snapshots.

Слияние этого пакета в delivery repository не означает интеграцию patch в upstream, готовность к production или compile/test/runtime PASS.
