# Долговременная память и временный worktree: подтверждённый lifetime-конфликт

Дата: 2026-11-13. Core remote HEAD: `89997df995df7c39b713e16aba216ecb19c8f497`; Modules remote HEAD: `3270dc0f894eaf4d0360306052b806099b8f5351`. Оба проверены через `git ls-remote origin HEAD`. Исходные checkout чистые; production не изменялся, ничего не опубликовано.

## Результат

**Подтверждён условный P2: успешно сохранённая долговременная память ребёнка удаляется обычным successful cleanup worktree.** Это дополнительный regression-сценарий к общей проблеме ownership/lifetime временных workspace, а не второй независимый P1 за тот же cleanup. Он не зависит от уже известных JSONL partial append или SQLite FTS query: оба backend проходят запись и немедленное чтение без ошибок, затем исчезает сам storage.

В поддерживаемой конфигурации `task` → один ребёнок с `isolation="worktree"`, `max_depth=1` и включёнными memory tools:

1. Core создаёт worktree и добавляет `/.proteus/` в общий Git exclude.
2. Реальный child memory component запускается в cwd worktree. Без `path` override используются `.proteus/memory.jsonl` либо `.proteus/memory.sqlite`.
3. Реальный `remember_fact` возвращает `ok=true / Remembered`; реальный `recall_memory` сразу возвращает сохранённый факт. Fixture проверяет наличие непустого файла до завершения child.
4. Child завершается успешно без изменений обычных файлов/HEAD. Git status не считает ignored `.proteus` изменением.
5. TaskTool вызывает настоящий Git cleanup: checkout и ветка удалены, root получает success с `[worktree: no changes, removed]`. Файла memory больше нет.

Здесь нет вложенного второго worktree, фоновых процессов-писателей, отмены, disk-full, fault injection или гонки. Достаточно штатного последовательного завершения. У JSONL сохранён один валидный complete record; у SQLite успешно завершён INSERT и readback.

## Проверки и контроли

Все восемь сценариев прошли через настоящий `proteus server stdio` → synthetic workflow/v20 → обычный `host.tools.execute_batch` с явным fixture allow-all policy → реальный memory component. Сам `task`, child process, смена cwd и Git cleanup настоящие. Модель не вызывается.

| Backend | Child isolation / storage | Запись и recall до возврата | Файл после возврата | Child checkout | Recall из root |
|---|---|---:|---|---|---:|
| JSONL | Worktree, default path | 1 факт, оба success | **удалён** | удалён | 0 |
| SQLite | Worktree, default path | 1 факт, оба success | **удалён** | удалён | 0 |
| JSONL | Worktree, absolute path вне checkout | 1 факт, оба success | сохранён | удалён | 1 |
| SQLite | Worktree, absolute path вне checkout | 1 факт, оба success | сохранён | удалён | 1 |
| JSONL | Worktree, дополнительный untracked файл | 1 факт, оба success | сохранён | сохранён | 0 |
| SQLite | Worktree, дополнительный untracked файл | 1 факт, оба success | сохранён | сохранён | 0 |
| JSONL | Общий cwd, default path | 1 факт, оба success | сохранён | сохранён | 1 |
| SQLite | Общий cwd, default path | 1 факт, оба success | сохранён | сохранён | 1 |

Отсутствие факта в root само по себе **не объявляется багом**: default paths в разных workspaces намеренно различаются, это видно и в dirty control. Доказательство дефекта — physical removal только что подтверждённого durable store после success. Absolute/shared controls показывают, что backend и запрос чтения работают. Dirty controls дополнительно фиксируют `!! .proteus/` в настоящем `git status --ignored`.

## Цепочка исходников

Core:
- [`process_adapters/config.rs:68–78`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/config.rs#L68-L78) и [`sandbox.rs:46–55`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/process_adapters/sandbox.rs#L46-L55): default component cwd определяется workspace.
- [`agent_control/workspace.rs:21–23,43–56`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L21-L56) и [`151–180`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L151-L180): `.proteus` исключается из Git status общим exclude, распространяющимся и на worktree.
- [`task/workspace_lifecycle.rs:76–91`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L76-L91): Completed без cancellation разрешает cleanup.
- [`workspace.rs:105–134`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L105-L134): clean status/HEAD ведут к `git worktree remove`; durable ignored state отдельно не учитывается.

Modules:
- [`memory-pack/src/lib.rs:71–73,96–115`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/memory-pack/src/lib.rs#L71-L115): JSONL default path и успешная запись файла.
- [`sqlite-memory/src/lib.rs:35–36,78–95`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/sqlite-memory/src/lib.rs#L35-L95): SQLite default path и open/create базы.
- Оба [`memory-pack/src/tools.rs`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/memory-pack/src/tools.rs) и [`sqlite-memory/src/tools.rs`](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/context_provider/sqlite-memory/src/tools.rs) описывают remember_fact как durable long-term memory для фактов, переживающих turns/sessions, а не временный рабочий cache.

## Условия и ограничения

- **Stock `codex-coder` сейчас не экспонирует `remember_fact`**: [`configs/fragments/codex-coder-peer.toml:20–21`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/configs/fragments/codex-coder-peer.toml#L20-L21). Нужен custom child profile, явно включающий memory tools, как в fixture. Не утверждается, что stock coder теряет память в каждом запуске.
- В отличие от nested-worktree сценариев, здесь достаточно `max_depth=1`, совпадающего с default. Это не делает весь default profile затронутым: см. предыдущий пункт.
- Весь fixture synthetic, temporary Git/HOME/config. Нет пользовательских файлов, внешних API, live LLM, Desktop, concurrency stress или полной системной проверки.
- **Подтверждено удаление memory store, не доказано исчезновение текста из всех возможных источников.** Tool output/history могут хранить копию факта, а fixture намеренно записывает его в evidence. Ручное восстановление из transcript возможно; автоматическая память уже не содержит этого факта.
- SQLite connection может ещё удерживать уже unlink-нутый inode до закрытия worker; это не сохранённый доступный файл и не durable store после перезапуска. Cold crash/reboot не моделировались.
- Разные per-export module_config и раздельные default stores сами по себе не объявлены ошибкой. Никакой автоматической глобализации памяти или передачи фактов между несвязанными проектами не предлагается.
- Подготовительная попытка контрольного config явно задать `isolation="none"` была отвергнута валидатором. Runner исправлен на отсутствие optional isolation; это ошибка fixture, не находка продукта. Финальные 8 runs успешны.

## Направление исправления

Отделить owner/lifetime долговременного module state от disposable source checkout. Варианты должны сохранить явную scope-семантику: стабильный project/task-owned storage, binding durable data root, либо сохранение worktree при наличии durable side effects. Не надо специальных проверок `jsonl_memory`/`sqlite_memory` в Core и автоматического объединения памяти всех агентов.

Практическая конфигурационная мера для сознательно разделяемой памяти — явный абсолютный путь вне disposable worktree, как положительный контроль. Это выбор владельца storage scope, не универсальная автоматическая миграция.

Регрессионный контракт: авторизованный child запомнил факт, смог его прочитать, завершился success; normal cleanup не должен молча уничтожать заявленную долговременную память. Покрыть оба backend, configured external path, clean/dirty checkout и обычный shared cwd. Перенос worktrees из вложенной `.proteus/worktrees` в общий каталог сам по себе **не исправит** memory внутри каждого checkout.

## Воспроизводимость и artifacts

- `workflow.py` — только model-free orchestration и внешние evidence markers; не эмулирует memory.
- `run.py` — создаёт свежие временные repos/configs, запускает 8 stdio/process сценариев.
- `*-markers.jsonl`, `*-outputs.json`, `*-summary.json`, `*-stderr.log` — полные реальные ответы и before/after состояние.
- `verify.py` — диагностические assertions, намеренно подтверждающие текущий дефект и контроли.
- `verification.log`: **8/8 PASS** диагностик.
- `expected-failure.log`: `--expect-fixed` ожидаемо FAIL (`successful durable memory was deleted by normal task cleanup`).
- `provenance.txt`: точные SHA256 binaries, исходные SHA, timestamp.

```bash
python3 /workspace/shared/memory-workspace-lifetime-evidence/run.py
python3 /workspace/shared/memory-workspace-lifetime-evidence/verify.py
python3 /workspace/shared/memory-workspace-lifetime-evidence/verify.py --expect-fixed
```

Runner использует уже собранные неизменённые Core/memory binaries по указанным путям, Core allow-all policy и Python component_runtime fixture. Для переноса пути нужно направить на эквивалентные pinned artifacts. Modules компилировались с собственным неизменённым Core dependency pin `b5fac84245b075896c24763b3aebac79b4375c2e`, а не подменённым dependency main. Core executable проверен до/после запуска; production исходники чистые. Cargo/full gate не запускался повторно, поскольку production не менялся и готовые реальные binaries покрывают нужную границу.

Просмотрены JSONL/SQLite store, provider, tools; context-pack retrieval/budget; process component workspace binding; child cwd/workspace preparation; cleanup и профильные tool restrictions. Старые partial append и FTS punctuation не пересчитаны. Других новых доказанных memory/runtime дефектов этот проход не заявляет.
