# P2: task сообщает старую ветку вместо ветки с commit ребёнка

## Версия и метод

Core remote HEAD: `89997df995df7c39b713e16aba216ecb19c8f497`.
Неизменённый binary SHA-256 `09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`.
Git 2.52.0. Полная provenance в `provenance.txt`, remote check в `remote-head.txt`.

Реальные root `proteus server stdio`, TaskTool/ToolOrchestrator, ProcessAgentControl,
отдельный полный child peer, обычный Git. Синтетический workflow делает строго
заданный небольшой edit/commit, затем возвращает успех. `max_depth=1`.
Никаких production правок, публикации, live models или пользовательских репозиториев.

## Основная находка: stale integration target

1. Root делегирует задачу worktree-role `coder`; runtime создаёт ветку `proteus/coder-call_0`.
2. Child делает `git switch -c feature/implementation`, меняет tracked `base.py`,
   коммитит результат и успешно заканчивает turn.
3. Cleanup сохраняет checkout, но facade выдаёт:
   ```text
   [worktree: .../coder-call_0 | branch: proteus/coder-call_0]
   The subagent's changes live only on that branch. Review and merge it yourself, then remove the worktree.
   ```
4. Названная ветка содержит **исходный** `BASE = True`. Реальный результат находится
   только в `feature/implementation`, которая в добавленной Core-инструкции не названа.
5. Выполненный в fixture root `git merge --ff-only proteus/coder-call_0`
   отвечает `Already up to date.`. Root остаётся без реализации.
6. Follow-up через тот же task_id успешно достигает того же child/session, но снова
   получает от facade то же ошибочное направление merge.

P2: ложная ссылка на результат и неправильная инструкция интеграции при штатном
Git branch switch. Это **не коллизия call_id/branch name** из предыдущего отчёта.
Данные в данном сценарии сохранены; не утверждается потеря commit.

## Контроль

При тех же действиях без `git switch` child коммитит в исходную worktree branch.
Facade указывает правильную ветку, resume работает, её fast-forward merge переносит
реальную правку в fixture root. Отличие ровно в смене child branch.

## Связанный regression: rename лишает facade resume

`git branch -m feature/implementation` вместо switch приводит к другой ветке этой
же stale identity проблемы:

- результат child committed и checkout существует;
- cleanup пытается `rev-parse --verify refs/heads/proteus/coder-call_0` и ошибается;
- TaskTool возвращает `ok=true`, `status=completed`, `resumable=true` и
  `[worktree cleanup failed: failed to resolve saved worktree branch ...]`;
- текстовый task_id не выдан;
- явная попытка resume по реальному `metadata.child_thread_id` немедленно
  отвергается: `worktree ... is gone (removed, merged, or lost on restart)`;
- реальный checkout и commit в `feature/implementation` никуда не делись.

Это дополнительный терминальный trigger потери facade workspace mapping,
**не новый независимый P1 поверх уже обнаруженного pre-dispatch resume-loss**.
Прямой backend resume в этом конкретном rename-прогоне не проверялся. Доказан
отказ facade при сохранном checkout и объявленном backend `resumable=true`.

## Причина и направление исправления

`crates/proteus-core/src/core/agent_control/workspace.rs`:
- `create_worktree` запоминает initial `branch` в WorkspaceInfo (`:44-61`);
- cleanup сверяет saved ref, не актуальную symbolic HEAD (`:81-91`);
- несовпавший HEAD сохраняет checkout, но не обновляет branch identity (`:114-117`).

`task/workspace_lifecycle.rs:224-228` без проверки печатает `info.branch` как
единственную ветку с результатом. `:236-240` при cleanup error не регистрирует
существующий checkout для resume.

При finalization следует различать managed original branch и фактическую
HEAD/branch identity. Не обещать, что commit лежит в initial ref, если child
перешёл на другую ветку или detached HEAD. Если branch identity изменена,
явно сообщать проверенный target/commit либо просить ручную проверку, не
выдумывая корректный merge. Безопасность cleanup и восстанавливаемость checkout
после обратимой Git-ошибки должны проверяться отдельно.

## Прогоны и файлы

Каждый из трёх сценариев выполнен дважды на свежих fixture-репозиториях:
`branch-original`, `branch-switched`, `branch-renamed`. Первый набор `repeat1/`,
второй в корне evidence. Каждый root делает initial task и follow-up;
в renamed follow-up отклоняется до нового child turn.

- `python3 verify.py`: observed outcomes подтверждены в 6 сценариях.
- `python3 verify.py --expected-safe`: намеренно красный инвариант,
  что названная ветка действительно интегрирует committed child result.
- `run.py`, `worktree_fixture.py`: воспроизведение.
- `*-markers.jsonl`: original/current branch, commit, task/followup results.
- `*-outputs.json`: raw transport.
- `*-summary.json`: состояние файлов/веток, фактический merge результат.
- `verification.log`, `expected-safe-failure.log`: тестовые итоги.

Runner принимает `PROTEUS_BINARY` и `PROTEUS_REFERENCE_MODULE`.

## Ограничения

Проверены указанный Linux/Git и Core HEAD. Живая модель не использовалась:
насколько часто она меняет ветку внутри worktree, этот тест не измеряет.
Полный Rust gate/UI не запускались. В отчёте нет production patch или коммита.
