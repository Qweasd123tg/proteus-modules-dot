# Nested task worktrees: successful ancestor cleanup deletes a retained descendant

Дата: 2026-11-13. Remote Core HEAD сверён: `89997df995df7c39b713e16aba216ecb19c8f497` (`remote-head.txt`). Production-код не менялся, commit/push/PR не выполнялись.

## Подтверждённая находка: P1 при разрешённой вложенности worktree-задач

**Чистый worktree родителя удаляется вместе с уже успешно завершившимся, грязным worktree потомка. Незакоммиченный результат потомка исчезает, хотя его task только что сообщил, что checkout сохранён и доступен для review/resume.**

Точная цепь:
1. Root вызывает `task` с `isolation="worktree"` и создаёт parent checkout.
2. Parent синхронно вызывает ещё один `task` с `isolation="worktree"`.
3. Leaf пишет новый незакоммиченный файл и успешно завершает свой turn. Его lifecycle видит грязный checkout, сохраняет его и возвращает `[task_id: ...]` и `[worktree: ... | branch: ...]`.
4. Parent получает этот результат, ничего не меняет в собственном checkout и успешно заканчивает turn.
5. Parent cleanup считает checkout чистым и вызывает обычный `git worktree remove` **без `--force`**. Git рекурсивно удаляет и вложенный leaf checkout.
6. Root получает `ok=true` и `[worktree: no changes, removed]`. Ранее обещанный leaf path уже отсутствует. Его ветка остаётся на исходном commit и не содержит созданного файла.

Это последовательный штатный сценарий: **нет гонки, отмены, reload, ошибки dispatch, фонового ребёнка или неожиданного выхода процесса**. Нужны разрешённая глубина хотя бы два перехода и два уровня worktree isolation. В fixture `max_depth=3`; default `max_depth=1` не допускает эту цепь.

### Три настоящих process-прогона

| Сценарий | Root turn | Leaf-файл после turn | Данные в leaf branch |
|---|---|---|---|
| Чистый parent, незакоммиченный leaf | Success | **Удалён** | Нет, `git show branch:file` завершается 128 |
| Parent имеет свой untracked edit, незакоммиченный leaf | Success | **Сохранён** | Нет, и это нормально: файл есть в checkout |
| Чистый parent, leaf закоммичен | Success | **Checkout удалён** | Да, commit и файл восстанавливаются из ветки |

В первом и третьем случаях `git worktree list --porcelain` оставляет запись leaf с `prunable gitdir file points to non-existent location`. Во всех трёх случаях inner task до parent cleanup вернул success, retained worktree и task_id; все три workflow-level finish зафиксированы.

Фрагмент root output первого сценария:

```
Leaf result is in valuable-result.txt
[task_id: ...]
[worktree: .../parent/.proteus/worktrees/leaf | branch: proteus/leaf]
The subagent's changes live only on that branch. Review and merge it yourself, then remove the worktree.
[worktree: no changes, removed]
```

После него `leaf_exists=false`. Сохранённая branch сама по себе **не сохраняет незакоммиченный файл**. Не утверждается, что реальный пользователь уже потерял данные или что содержимое никогда нельзя восстановить из отдельного журнала/бэкапа. Подтверждено удаление рабочей копии и отсутствие новых данных в Git-ветке.

## Причина и ссылки на точный SHA

- [`workspace.rs:28–41`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L28-L41): `git rev-parse --show-toplevel` в parent worktree возвращает **parent checkout**, не главный checkout общего repository. Новый путь становится `parent/.proteus/worktrees/leaf`.
- [`workspace.rs:153–177`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L153-L177): shared Git `info/exclude` содержит `/.proteus/`; поэтому вложенный checkout не виден в обычном status parent.
- [`task/workspace_lifecycle.rs:169–178`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L169-L178): новый child создаётся от `request.task.cwd`, затем cwd подменяется новым checkout. На следующем уровне путь действительно вложенный.
- [`workspace.rs:105–134`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L105-L134): cleanup проверяет только branch/status/HEAD текущего parent. Наличие retained descendant worktrees не проверяется. `git worktree remove` игнорируемое поддерево удаляет без `--force`.
- [`task/workspace_lifecycle.rs:76–91`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L76-L91) и [`205–228`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L205-L228): successful parent допускает cleanup, а результат публикует «no changes, removed». Child ранее независимо выдал retained note.
- [`configuration.md:1311–1317`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1311-L1317): глубина вложенности является поддерживаемой настройкой.

Это не ранее найденные facade mapping loss при pre-dispatch Err, pool reset при reload или потеря событий фонового внука. Здесь реально уничтожаются файлы уже завершившегося потомка при успешной последовательной работе.

## Направление исправления

Главный инвариант: lifecycle одного task не вправе удалять checkout, принадлежащий другому task, включая уже завершённые retained results.

- Предпочтительно создавать все worktrees в стабильном общем owner-root вне удаляемых task checkout, сохраняя правильный base commit текущего parent. Нельзя просто всегда ветвиться от HEAD главного checkout: это изменит семантику делегирования из изменённой parent branch.
- До такой смены layout запрещать cleanup ancestor с существующими зарегистрированными descendant worktrees/retained owners. Проверка только dirty status недостаточна; проверка только активных процессов тоже недостаточна, потому что воспроизведённый leaf уже завершён.
- Нужен boundary regression: root → worktree task → worktree task; leaf uncommitted и committed, parent без своих изменений; данные и обещанный retained checkout сохраняются. Контроль clean single-level cleanup должен оставаться рабочим.

Production patch в этом исследовании не делался; точный способ координации cross-process ownership требует отдельной реализации и её проверок.

## Evidence, воспроизведение, ограничения

Каталог `/workspace/shared/workspace-lifecycle-evidence`:
- `worktree_fixture.py`: model-free workflow-v20 component, запускающий два настоящих `task` через `host.tools.execute_batch`.
- `run_worktrees.py`: создаёт полностью синтетические Git repositories/HOME/configs, запускает настоящий `proteus server stdio`, собирает outputs, marker logs и состояние Git **до shutdown**.
- `*-outputs.json`, `*-markers.jsonl`, `*-summary.json`, `*-stderr.log`, `run.log`: результаты трёх проверок.
- `verify.py`, `verification.log`: все наблюдения и положительный контроль прошли assertions.
- `expected-regression-failure.log`: `verify.py --expect-fixed` ожидаемо падает на desired invariant `parent cleanup deleted nested uncommitted leaf result`.
- `provenance.txt`: source SHA, clean status, SHA256 бинарника/reference fixture и Git version. Бинарник скопирован из ранее свежесобранного `command-workflows-target/debug/proteus`; SHA256 совпадает с `command-workflows-evidence/binary-sha256.txt`. Его исходный production-код был неизменённым на указанном SHA. Изолированная копия binary исключает подмену общим target во время проверок.
- `setup-attempt/`: первый подготовительный прогон до корректной передачи пути marker file. Ошибка `'WORKTREE_PROBE_MARKERS'` была ошибкой fixture: произвольная env переменная не попадает в module worker. Итоговые прогоны передают marker path аргументом; setup failures не считаются продуктной находкой.

Команды в текущем workspace:

```bash
python3 /workspace/shared/workspace-lifecycle-evidence/run_worktrees.py
python3 /workspace/shared/workspace-lifecycle-evidence/verify.py
python3 /workspace/shared/workspace-lifecycle-evidence/verify.py --expect-fixed
```

Для переноса заменить локальные пути Core/component_runtime, policy fixture, binary и reference module в двух скриптах. Каждый запуск создаёт новые временные repositories и не трогает пользовательские исходники.

**Граница:** реальный TaskTool/ToolOrchestrator, explicit allow-all fixture policy, ProcessAgentControl, stdio peers, Git worktree creation/finalization. Запись leaf-файла является test-only синтетическим действием workflow, не реальным model/patch-tool решением; cleanup не замокан. Модели, внешняя сеть, Desktop и пользовательский harness не использовались. Нагрузочный/конкурентный тест и полный Rust gate не запускались; уже найденная последовательная потеря не требует concurrency. Durable session cold replay в этой серии отдельно не проверялся.
