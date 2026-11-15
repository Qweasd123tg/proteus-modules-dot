# TaskTool: показывать незавершённый lifecycle outcome модели

## Статус

**Source-only candidate для известного `task-terminal-status` из PR85**, не новая
находка и не проверенный runtime fix. Исправление сосредоточено в существующей
model-facing TaskTool projection, а не в process lifecycle или новом framework.

Свежие refs на 2026-11-15: Core
`bcbda4435534a296c707a1daa250813d692f68e1`, Modules
`c035142558f0fca43e9772fc0e50ca293abf1531`, delivery
`657e0a43947e6fbde5b48a7af1856dddbfc4ba4f` (PR113).
PR113 A1 остаётся отдельным некомпилированным Modules proposal, не решает OTM-1.
Данный patch предназначен для указанного Core main, не меняет Modules pin и не
заявляет совместную сборку репозиториев.

## Причина

`AgentControlResult` уже содержит typed `AgentLifecycleStatus`. Process runner
отдельно сохраняет partial text и возвращает `TimedOut`/`Cancelled`, а task facade
добавляет resume/worktree сведения. Но общий `result_to_tool_result` безусловно
создаёт `ToolResult::ok`, оставляя status только в metadata.
`text_or_status()` и native provider projection не включают metadata, поэтому
пустой timeout выглядит как успешный `(no output)`, а partial text как обычный ответ.

Подтверждённый старый process/HTTP сценарий опубликован в [PR85](https://github.com/Qweasd123tg/proteus-modules-dot/pull/85)
и используется только для provenance и dedup. Он не запускался заново и не доказывает работу
этого candidate на свежем SHA.

## Выбранный contract

- Только `Completed` возвращает `ToolResult::ok`. Текст, порядок suffix и empty
  success semantics у completed результата остаются прежними.
- Любое другое typed состояние возвращает `ToolResult::error` с наблюдаемым
  canonical status, предупреждением «completion was not confirmed», указанием
  на возможную неполноту summary и уже выполненные действия.
  Внешний Rust результат invocation остаётся `Ok(ToolResult { ok: false, .. })`,
  не `Err`: обычная обработка и запись tool result продолжаются.
- `Starting`, `Running`, `Unknown` не переименовываются в `Errored` и не описываются
  как rollback или доказанное отсутствие действий. Error означает отсутствие
  подтверждённого завершения запрошенной задачи, а не знание всех её последствий.
- Полная имеющаяся summary, разрешённый upstream formatter-ом `task_id` и
  workspace note находятся **в одном error-поле**. Разделение status в error и
  partial summary в output снова скрыло бы summary из-за error precedence.
- Canonical enum сериализуется один раз; тот же status Value сохраняется в
  metadata. Child thread/session metadata и resume policy не меняются. Новой
  таблицы status labels, enum, публичного DTO или общего formatter framework нет.
- Model-facing spec и существующая русская runtime документация объясняют
  результат и необходимость проверить последствия перед повтором задачи.

Это намеренное изменение `ok/error` semantics для non-completed результатов,
не чистый refactor и не обещание экономии строк или памяти. Production task.rs
183 → 200 строк, spec.rs 90 → 91; исправляется семейство известных и будущих
non-Completed вариантов одной проверкой существующего typed status.

## Проверенные safe boundaries и ограничения

Worktree finalizer принимает cleanup/resume решение по `AgentControlResult.status`
**до** вызова изменённого formatter. Его policy, cancellation, retained path и
branch notes не меняются. В данном pass worktree операции не выполнялись.

В прочитанных Core invocation/finish/record-result и Modules coding execute/
append-result путях `ok=false` не запускает автоматический retry. Это обычный
tool result, остающийся в canonical/model history. Указанное не гарантирует
поведение произвольных внешних hooks/workflows или решения последующей LLM.
Host-level `Err`, отмена всего invocation и внешние timeout races остаются
существующими отдельными ветками; patch не обещает восстановить отсутствующий
partial result, если backend его не вернул.

Core `truncate_result` ограничивает error и output отдельно прежним byte budget.
Новый prefix расходует часть бюджета; downstream truncation/hooks могут убрать
часть summary, task_id или worktree note. Полное сохранение доказуемо только
на уровне formatter **до** этих transformations. При очень малом бюджете нельзя
обещать даже целый status header. Новый aggregate budgeting contract не вводится.

Native OpenAI/Anthropic request serializers используют `text_or_status()`, а
Anthropic также `is_error = !result.ok`; поэтому исправление попадает в уже
существующую model-facing projection. В PR113 ветка без Image сохраняет этот
путь. Это source reasoning, не actual-wire/live-provider test данного candidate.

## Проверка и evidence

- `SOURCES.json`: 26 точных Core/Modules blobs,
  Git blob identities совпали. Не означает execution coverage всего файла.
- `task-terminal-outcome.patch`: два production Rust файла,
  один test файл, существующая runtime документация.
- Три новых proposed tests: все шесть текущих non-Completed статусов; пустой
  timeout и прежний empty-completed контроль; `TaskTool::invoke` с mock host,
  вернувшим timeout + partial summary. Existing completed/session test усилен
  exact output/ok/error assertions; spec test дополнен новой semantics.
  **Ни один тест не запускался.**
- `PATCH-VERIFICATION.json`: `git apply --check`, text apply и byte comparison
  четырёх after files в изолированной копии, без исполнения проекта.
- `COMPOSITION.json`: оба text-only порядка с Core PR111 candidate применились
  и дали одинаковые bytes. Это не доказательство compile/runtime integration.
- `TASK-OUTCOME-INDEPENDENT-REVIEW.md`: независимое exact source review.

Rust/cargo/rustfmt/clippy, project scripts, tests, process/provider runtime и
installs не выполнялись; upstream production и remote refs не менялись.
До принятия нужны formatting/compilation, targeted task tests и имеющийся
process-agent-control/native-wire regression с timeout, partial text и completed
control на точных версиях. Семейство output-budget/completion consumption этим
patch не исправляется.
