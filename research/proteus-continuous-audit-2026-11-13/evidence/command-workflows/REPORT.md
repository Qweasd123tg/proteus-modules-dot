# Task/worktree resume: transient admission failure destroys facade binding

Дата проверки: 2026-11-13. Core remote HEAD повторно проверен: `89997df995df7c39b713e16aba216ecb19c8f497` (см. `remote-head.txt`).

## Подтверждённая находка: P2

**Временный отказ `max_parallel` необратимо отключает resume уже завершённой worktree-задачи через `task`, хотя backend сохраняет процесс, историю и checkout.**

Это одна root-cause группа с двумя независимо проверенными триггерами, не два бага:

1. У уже завершённой worktree-задачи есть рабочий `task_id`. Другой запуск занимает единственный разрешённый слот `max_parallel=1`. Попытка resume получает штатный отказ о лимите. После освобождения слота повтор того же корректного resume уже получает `worktree ... is gone ... start a fresh task instead`.
2. Тот же существующий `task_id` по ошибке передан с другой существующей worktree-ролью. Backend корректно отвергает роль **до dispatch**, но исправление `agent_type` уже не помогает: facade потерял mapping. Контроль с ошибочной **non-worktree** ролью не ломает следующий правильный resume.

Результаты настоящих boundary-прогонов:

```
capacity full: ok=false, error="too many concurrent subagent children (max_parallel 1)..."
capacity freed: retry ok=false, error="worktree for task_id ... is gone ..."
after capacity reject: same backend resume ok=true, checkout_present=true

control wrong shared-role then corrected resume: ok=true
wrong worktree role: ok=false, error="task_id belongs to agent profile coder_a, but request profile is coder_b"
corrected worktree role: ok=false, error="worktree for task_id ... is gone ..."
same backend task_id remains resumable=true, checkout_present=true, new_children_on_rejection=0
```

### Причина и взаимосвязь

`task` владеет своим process-global индексом `task_id -> WorkspaceInfo`. `prepare_workspace()` забирает `record.info.take()` **до** `host.run_agent()`. В случае любого `Err` `error_result_with_workspace()` удаляет запись task_id, даже когда child не запускался и backend корректно откатил admission.

У backend другой индекс. Для `max_parallel` путь такой: `prepare()` успешно резервирует idle child → `pending.reserve()` возвращает ошибку лимита → `SpawnReservation::drop` возвращает child в idle pool с прежним task_id. Но facade ошибочно теряет свою половину resume-состояния. В случае неверной роли backend отказывает ещё раньше, не меняя свой pool.

Исходники текущего SHA:
- [Захват worktree mapping до child admission](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L135-L178)
- [Любой host Err идёт в общий error path](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L76-L97)
- [Удаление прежнего task_id в error path](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L247-L270)
- [Backend резервирует resume, затем проверяет общий cap](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/mod.rs#L566-L603)
- [Backend откатывает reservation при ошибке](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/reservation.rs#L27-L42)
- [Rollback сохраняет previous binding, если idle cap позволяет](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/pool.rs#L167-L187)
- [Несовпадение роли отвергается до lease](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/pool.rs#L93-L107)

### Пользовательское последствие

Обычный исправляемый отказ становится постоянной потерей возможности продолжить конкретную task-задачу с накопленным контекстом через публичный `task` facade. В сообщении предлагается стартовать новую задачу, хотя старая фактически жива. Данные checkout и файл с синтетическим результатом **не удалены**. Не заявляется потеря сохранённой истории на диске или повреждение git-ветки.

Это **не** прежняя находка `ReloadTools` → сброс всего process pool. Здесь reload отсутствует, backend и child остаются действительными, ошибка ограничена согласованностью двух resume-индексов.

### Что исправлять

Нужен различимый результат admission: backend должен сообщать, что отказ случился до dispatch и прежний resume сохранён после rollback. На таком исходе facade возвращает `WorkspaceRecord.info`, аналогично уже существующему `restore_unstarted_resume` для cancel до dispatch. Нельзя безусловно восстанавливать mapping на любом `Err`: после реального child failure активные эффекты могут ещё завершаться, а history мог быть инвалидирован. Одной проверки неправильной роли недостаточно: воспроизведённый `max_parallel` failure возникает уже после reserve_resume и должен откатываться вместе с facade-резервацией.

Сохранить существующие гарантии concurrent resume ownership, cancellation/late effects, safe worktree cleanup.

## Точная граница воспроизведения

Изолированная копия: `/workspace/shared/command-workflows-audit`. Единственное добавление — тестовый integration target `crates/proteus-core/tests/command_workflow_review.rs`. Production-исходники не менялись; commit/push/PR не выполнялись.

Используются реальные `AgentControlRuntime::register_tools`, штатный `TaskTool`, `ProcessAgentControl`, Git worktree, настоящий дочерний `proteus server stdio`, штатный fake model component. Test-only `ForwardingHost` только передаёт request в реальный backend с фиксированным test context и при первом запуске пишет синтетический `retained-result.txt`, чтобы production cleanup оставил checkout и выдал task_id. Роль/лимит/rollback ошибки не симулируются.

Для cap-case test-only event sink удерживает **другой** реальный `spawn()` после `pending.reserve` и перед dispatch, детерминированно занимая слот без sleeps. Затем gate отпускается, blocker штатно заканчивается, после чего выполняются failed facade retry и успешный backend control. Это проверка admission ordering, не нагрузочный тест.

Тест вызывает зарегистрированный tool напрямую; слой policy/approval/ToolOrchestrator не является предметом доказательства. Реальные аккаунты/платные модели/сеть/GUI не использовались. Полный workspace gate и пользовательский harness не запускались.

## Проверки и артефакты

- Штатный focused baseline `process_agent_pool_`: **9 passed / 0 failed**, `baseline.log`.
- Два новых regression теста проверяют желаемый инвариант и **ожидаемо падают** с приведёнными продуктными симптомами, `repro-both.log`.
- Оба сценария повторены ещё три раза со свежесобранным binary из этой isolated-копии: каждый раз **2 expected failures**, `repeat-{1,2,3}.log`.
- Первоначальный `repro.log` содержит только сценарий роли; начальный прогон использовал уже существующий binary того же production SHA. Повторные прогоны используют `/workspace/shared/command-workflows-target/debug/proteus`, собранный здесь из неизменённого production-кода.
- `binary-sha256.txt` фиксирует binary и reference module. `reproduction.patch` добавляет только integration tests. `git diff --check` чистый.

Команда после применения patch (пути binary и fixture заменить локальными):

```bash
PROTEUS_TEST_BINARY=/path/to/proteus \
PROTEUS_TEST_REFERENCE_MODULE=/path/to/proteus-reference-module \
python3 scripts/test.py -p proteus-core --test command_workflow_review repro_worktree_ -- --nocapture
```

## Охват чтения этого прохода

Повторно просмотрены CLI slash dispatch/parser/client, AppServer command catalog/run admission/operations, runtime detached commands/execution/conversation, ACP prompt/input и AgentControl task/workspace, process pool/reservation/turn/output/messaging/history/pending/mailbox. Это целевой boundary-аудит, не утверждение о полном новом прочтении всех репозиториев. Известные CLI stale-input, slash hot-reload collision, worktree trailing-space, nested-event и reload defects не пересчитаны как новые.
