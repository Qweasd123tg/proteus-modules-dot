# P1: `status.showUntrackedFiles=no` уничтожает новые исходники worktree-задачи

## Проверенная версия и граница

Core remote HEAD повторно проверен: `89997df995df7c39b713e16aba216ecb19c8f497`.
Исполнен неизменённый binary, собранный из этого HEAD; SHA-256:
`09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`.
Git 2.52.0. Полные пути и reference-fixture SHA в `provenance.txt`.

Это реальный `proteus server stdio` → policy/ToolOrchestrator → `TaskTool` →
`ProcessAgentControl` → отдельный полный stdio peer → Git-worktree cleanup.
Вместо live model использован маленький детерминированный workflow/v20 fixture:
child записывает обычный новый Python-файл и успешно заканчивает turn.
Никакие production sources не изменены; всё исполняется в отдельных временных репозиториях.

**Это не известный nested-worktree дефект**: только один child, `max_depth = 1`,
новый файл не ignored и не лежит в служебной `.proteus` внутри child checkout.
Не нужны race, отмена, crash, child branch switch или фоновый процесс.

## Воспроизведение

1. Обычный Git-репозиторий с одним commit и tracked `base.py`.
2. Установить штатную Git-настройку: `git config status.showUntrackedFiles no`.
3. Дать worktree-isolated роли задание создать новый `new_algorithm.py`, без staging/commit.
4. Child успешно записывает файл с уникальным содержимым. Перед возвратом:
   - `git status --porcelain` возвращает пустую строку;
   - `git status --porcelain --untracked-files=all` возвращает `?? new_algorithm.py`.
5. Parent возвращает `task.ok=true`, `metadata.status=completed` и:
   `[worktree: no changes, removed]`.
6. Сам файл, checkout и исходная worktree branch уже удалены. Новый файл никогда
   не был в commit/index, поэтому ветка/обычное Git-восстановление не содержат результат.

Git config задан только локально в fixture, пользовательские settings не тронуты.
Валидный `.gitignore` не скрывает файл: explicit-all status доказывает, что это именно untracked, не ignored.

## Два независимых повтора и контроли

Каждый сценарий исполнен дважды в свежем репозитории (8 реальных root→child прогонов).
Первый набор сохранён в `repeat1/`, второй в корне evidence.

| Сценарий | Итог child | Файл / checkout после task |
| --- | --- | --- |
| default Git config, новый unstaged файл | success | сохранены, выдан task_id |
| `showUntrackedFiles=no`, новый unstaged файл | success | **оба удалены**, ветка удалена |
| тот же config, новый файл после `git add` | success | сохранены, выдан task_id |
| тот же config, правка tracked `base.py` | success | сохранены, выдан task_id |

`python3 verify.py`: наблюдаемые outcomes совпадают во всех 8 сценариях.
`python3 verify.py --expected-safe`: ожидаемо падает инвариант
«обычный новый исходник должен сохраниться вне зависимости от настройки отображения Git status».
Логи: `verification.log`, `expected-safe-failure.log`.

## Причина

`crates/proteus-core/src/core/agent_control/workspace.rs:109` проверяет
`git status --porcelain` без explicit untracked visibility. Внешняя настройка UI Git
тем самым меняет destructive cleanup policy. Затем `:127` вызывает
`git worktree remove` без override. Git сам учитывает тот же config и **не служит
второй защитой**: команда удаляет checkout с непроиндексированным файлом без `--force`.

`task/workspace_lifecycle.rs:205-209` превращает Removed в «no changes».
Таким образом обычная display preference может превращать успешную coding-задачу в потерю данных.

## Направление исправления, не production patch

Не позволять display config влиять на критерий «checkout неизменён»:
явно включать untracked files при inspection. Для удаления также нужен
config override, например `git -c status.showUntrackedFiles=all worktree remove ...`:
иначе новый файл, появившийся между inspection и removal, остаётся без второй защиты.
В отдельной Git fixture такой override корректно отказал в удалении и сохранил файл;
`git-override-control.log` содержит exit 128 и retained=true.
Это не решение известных задач quiescence/nested ignored stores, для которых нужны отдельные инварианты.

## Ограничения

Проверен Linux/Git 2.52.0 и этот Core HEAD. Никаких live model calls, GUI или полного Rust gate.
Запись исходника синтетическая, но создание worktree, peer lifecycle, completion и cleanup полностью production.
Результаты ничего не утверждают о распространённости Git config у пользователя.
Никакой публикации, PR, коммита или production исправления здесь нет.

## Файлы и повтор

- `run.py`: 4 реальных stdio сценария, повтор запуском того же script.
- `worktree_fixture.py`: синтетическое поведение root/child.
- `component_runtime.py`, `process_allow_all_policy.py`: изолированные fixture helpers.
- `*-summary.json`: подтверждённые состояния после завершения root task.
- `*-outputs.json`, `*-markers.jsonl`, `*-stderr.log`: raw transport и evidence записи.
- `verify.py`: observed regression и намеренно красный desired invariant.
- `remote-head.txt`, `provenance.txt`: версия исходников/binary.

Для другого окружения runner принимает `PROTEUS_BINARY` и `PROTEUS_REFERENCE_MODULE`.
Reference module нужен только для валидного fake-model binding, модель в workflow не вызывается.
