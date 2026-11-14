# ReloadTools уничтожает возможность продолжения завершившегося subagent

## Статус

Подтверждено независимо на чисто собранном Core HEAD `89997df995df7c39b713e16aba216ecb19c8f497`.
Рабочая копия исходников чистая; production-файлы не менялись. Ничего не опубликовано.
Рекомендуемая приоритетность: P2 (нарушение продолжения задачи, не удаление durable history).

## Воспроизведение

Настоящие процессы `proteus server stdio`: root и child, настоящий Component Runtime v3,
workflow/v20 и обычный `host.tools.execute_batch` через policy/tool recorder.
Синтетический model-free workflow вызывает выбранный tool и сохраняет настоящий checkpoint;
child model-free со стандартным structural ответом. Сетевые модели и реальные секреты не используются.

1. Root с `[agent_control] surface = "task"`, role `helper`, `max_idle_processes=8`.
2. `task(prompt="first task", agent_type="helper")`: успех, `resumable=true`, возвращает `task_id`.
3. `task(..., task_id=тот же ID)`: успех, сохраняется тот же physical child session. Это положительный контроль.
4. `ReloadTools` при **неизменённом файле конфига**: успех, epoch `0 -> 1`, tool_names `["task"]`.
5. Тот же `task(..., task_id=...)`: ошибка `unknown task_id (expired or from another session)`.

Дополнительно тот же сценарий проверен для `surface="collaboration"`:
`spawn_agent -> wait_agent -> followup_task -> wait_agent` достигает generation 2,
после `ReloadTools` у `list_agents` исчезает `child_thread_id`, а `followup_task`
возвращает `collaboration agent '/root/worker' has no resumable task id`.

Обе поверхности воспроизведены по два раза на отдельной чистой сборке HEAD.
Ранее был один предварительный прогон на исходной debug-сборке с тем же результатом.
Это не эффект eviction: других детей не запускали, cap 8 не исчерпан, config не менялся,
root process/session не перезапускался.

## Причина и связка слоёв

- `crates/proteus-core/src/app_server/profile.rs:82-95`: ReloadTools готовит целиком новую assembly и публикует profile.
- `crates/proteus-core/src/core/registry.rs:123-127`: каждая сборка registry создаёт новый AgentControlRuntime.
- `crates/proteus-core/src/core/agent_control/mod.rs:55-67`: создаётся новый ProcessAgentControl.
- `crates/proteus-core/src/core/agent_control/process/mod.rs:131-141`: новый runner получает пустые ProcessPool/PendingChildren.
- `crates/proteus-core/src/core/runtime/reload.rs:77`: заменяется прежняя runtime assembly.
- `crates/proteus-core/src/core/agent_control/process/pool.rs:332-336`: Drop старого pool expires каждый retention token.
- `crates/proteus-core/src/core/agent_control/process/child.rs:58`: child process построен с kill_on_drop=true.
- Общий CollaborationControl сохраняет bounded presentation records, но не idle backend:
  `collaboration/control.rs:249-255` освобождает owner/handle по завершении.
  Idle `followup_task` использует **новый** current_host (`collaboration/message.rs:170`),
  поэтому просто сохранить старый отображаемый ID недостаточно.

Необязательное обновление tool-set задевает независимый session-owned peer lifecycle.
В отличие от documented отсутствия durable reattach после restart, здесь restart root отсутствует.

## Влияние и границы

Пользователь теряет resume обычного `task` или `followup_task` после штатного ReloadTools,
даже если agent_control не менялся. Уже записанная child history остаётся на диске;
не утверждаем её безвозвратное уничтожение. Путь full profile watcher также пересобирает registry
по коду, но отдельно в этом воспроизведении не запускался. Live-child, cancellation, GUI и реальные LLM
в этом прогоне не тестировались. Workflow replay не запускался; есть raw stdio + canonical journals.

## Исправление

Для неизменной конфигурации agent_control сохранять прежний session-owned backend/pool при reload,
не сохранять целый устаревший AgentWorkflowContext ради idle history. Если agent_control действительно
меняется, нужна явная семантика старых handles/resume binding. Не лечить только удалением history.expire():
это оставит ложную resumability при пустом новом pool и убитом child.
Regression: обе поверхности; успешный resume до/после no-op ReloadTools; ограниченность pool должна сохраниться.

## Артефакты

- `workflow.py`: локальный workflow/v20 fixture, без сетевых вызовов.
- `repro_reload.py`: end-to-end driver; binary можно передать первым аргументом;
  `AUDIT_SURFACE=task` выбирает обычный task, по умолчанию collaboration.
- `clean-head-run-{1,2}.log`: два collaboration-прогона.
- `clean-head-task.log`, `clean-head-task-2.log`: два task-прогона.
- `run-1794562892385443937/` и `run-1794562893256593324/`: clean collaboration wire/result/config/journals.
- `task-run-1794562922073830676/` и `task-run-1794562950029628852/`: clean task wire/result/config/journals.
- Clean build log: `/workspace/shared/trace-integration-round8-build.log`.
- Build command: `CARGO_TARGET_DIR=/workspace/shared/trace-integration-round8-target CARGO_PROFILE_DEV_DEBUG=0 cargo build --locked --offline -p proteus-core --bin proteus`.
- Binary SHA256: `4c1b478a7a989756684b85262af6b06b9f16eba1eb8b3b85a77cf8c908759180`.
