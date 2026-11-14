# Дополнительные границы nested task/worktree lifetime

Дата: 2026-11-13. Актуальный remote Core HEAD проверен через `git ls-remote origin HEAD`: `89997df995df7c39b713e16aba216ecb19c8f497`. Все пять прогонов используют неизменённый production binary именно этой версии. Никаких production edits, commit, push или PR. Все repositories, HOME/configs, marker files и данные синтетические.

## 1. P2: successful worktree cleanup уничтожает cwd активного read-only потомка

Новая проверенная граница: **root `task(worktree)` → parent `collaboration` → активный `spawn_agent(isolation=none, parallel_safe=true)` reader**.

Это не повтор уже известного сценария с двумя вложенными worktree и сохранённым dirty leaf. Здесь всего **один worktree**, нет незакоммиченного результата leaf, нет удаления вложенного checkout: read-only потомок продолжает использовать общий cwd собственного родителя.

Порядок задан явными внешними test-only барьерами, а не подобранным sleep:
1. Root запускает реальный task, создаётся worktree parent.
2. Parent запускает read-only peer через настоящий `spawn_agent`. Leaf подтверждает запуск, наличие tracked `base.txt` и ждёт внешнего барьера вне checkout.
3. Parent, убедившись, что leaf уже реально работает, завершает свой успешный foreground turn. Сам parent не менял checkout.
4. Root TaskTool удаляет parent checkout **и branch**, возвращает success и `[worktree: no changes, removed]`. Возобновляемый task_id facade не выдаёт.
5. Только после получения root response harness открывает барьер. Живой leaf пытается прочитать ранее существовавший tracked `base.txt` и получает `ENOENT`; `cwd.exists() == false`.

### Контроли

| Сценарий | Root response | Результат чтения leaf |
|---|---|---|
| Чистый parent, background reader | Success, checkout/branch удалены | **ENOENT, cwd отсутствует** |
| Dirty parent, background reader | Success, checkout сохранён, task_id выдан | Исходный tracked файл прочитан |
| Чистый parent, явный `wait_agent` | Success, cleanup после reader | Исходный tracked файл прочитан до удаления |

Файлы: `clean-background-*`, `dirty-background-*`, `clean-wait-*`, `run.log`.

### Причина и значение для исправления

- [`collaboration/mod.rs:150–202`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/collaboration/mod.rs#L150-L202): async spawn сохраняет parent task/cwd и возвращает Running receipt, не привязывая lifetime cwd к активному peer.
- [`process/mod.rs:474–515`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/process/mod.rs#L474-L515): Completed относится к foreground turn; процесс возвращается idle и остаётся живым. Это не доказательство отсутствия работающего descendant.
- [`task/workspace_lifecycle.rs:76–91`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L76-L91): Completed и отсутствие cancellation достаточны для разрешения cleanup.
- [`workspace.rs:105–134`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L105-L134): Git cleanliness/HEAD не проверяют активных потребителей checkout.
- [`task/workspace_lifecycle.rs:203–244`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L203-L244): после Removed фасад не сохраняет/не возвращает parent task_id, даже когда backend сообщает resumable.

**Следствие:** исправление предыдущей потери nested checkout простым переносом всех worktrees в общий стабильный каталог эту границу не исправит. Рабочая копия принадлежит ещё и живым пользователям общего cwd. Возможное направление: lease/reference ownership, отдельный явный lifecycle barrier либо сохранение checkout/parent handle, пока существуют активные разрешённые потомки. Нельзя считать `Completed` одного foreground turn эквивалентом quiescence дерева процессов. Это отдельный regression case для общей lifecycle-правки; не следует искусственно считать два cleanup manifestations двумя независимыми data-loss P1.

**Ограничения:** поддерживаемая конфигурация должна разрешать как минимум root→parent→leaf, в fixture `max_depth=3`; default `max_depth=1` такую цепь запрещает. Read-only проверяется по поведению fixture: leaf только читает tracked файл, marker/barrier IO происходит в отдельном test infrastructure. Нет фонового writer, внешнего процесса shell, live модели, Desktop или пользовательских данных. Само чтение синтетическое внутри workflow, не shipped file tool. Создание task/peer, admission/policy, процессы и destructive Git cleanup настоящие. Подтверждено прекращение доступа к cwd, **не новая потеря пользовательских данных**. Уже известная потеря delivery событий background grandson здесь не пересчитывается.

## 2. P2, условный: локальный tool call_id используется как глобальное имя Git branch

Worktree имя формируется только из `sanitize(role) + '-' + sanitize(call_id)`. Это же имя используется для ветки в общем Git repository. Session, parent, execution identity и случайный suffix отсутствуют.

В реальном nested process-прогоне root и parent являются **разными session** и каждый вызывает ровно один `task(next)` с локальным `call_id = call_0`. Это не повтор одного call внутри history/response.

- Outer task создаёт `proteus/next-call_0`.
- Inner task выбирает **другой вложенный путь**, но пытается создать ту же Git branch.
- Git отклоняет: `fatal: a branch named 'proteus/next-call_0' already exists`.
- Inner `ToolResult.ok=false`; leaf process не стартует. Outer workflow намеренно возвращает диагностический summary и заканчивает success; это поведение fixture, а не утверждение о том, как реальная модель обработает ошибку.
- Контроль с `root_call_0` и `parent_call_0`: inner `ok=true`, leaf стартует, оба clean checkout штатно удаляются.

Файлы: `identity-collision-*`, `identity-unique-*`, `identity-run.log`.

Ссылки:
- [`workspace_lifecycle.rs:169–177`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L169-L177) и [`308–323`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L308-L323): создание имени без session namespace.
- [`workspace.rs:35–57`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L35-L57): path проверяется локально, затем global branch создаётся через `worktree add -b`.

Направление исправления: считать worktree owner identity собственной глобально уникальной identity, а role/call_id оставить диагностическим префиксом. Альтернатива: включить session/execution namespace и обеспечить collision-free sanitization. Сама по себе замена вложенного path общим каталогом этот дефект не решает, только меняет его на более ранний `path already exists`.

**Ограничение приоритета:** фактическая частота зависит от генератора call IDs. Для глобально случайных UUID у моделей/fixtures вероятность отсутствует практически; здесь намеренно проверен валидный session-local генератор `call_0`. Live OpenAI/Anthropic не запускались и массовая частота им не приписывается. Это functional identity collision, не security finding и не ранее описанная UI/user-input collision: отказывает реальный Git workspace creation.

## Проверки и воспроизводимость

`python3 verify.py`: PASS, подтверждены все пять наблюдений и положительные контроли. Это **диагностические** assertions, green не означает исправление продукта.

`python3 verify.py --expect-fixed-lifetime`: ожидаемый FAIL, `cleanup removed cwd while descendant reader was still active`.

`python3 verify.py --expect-fixed-identity`: ожидаемый FAIL, `separate-session call ID collided in shared Git branch namespace`.

Команды из текущего workspace:

```bash
python3 /workspace/shared/nested-lifetime-evidence/run_lifetime.py
python3 /workspace/shared/nested-lifetime-evidence/run_identity.py
python3 /workspace/shared/nested-lifetime-evidence/verify.py
```

Каждый runner создаёт новые временные Git repos и HOME. Для переноса нужно указать существующий актуальный Core `proteus` binary, reference-module fixture, Python `component_runtime` и allow-all policy fixture из Core. Запуск не использует модель или внешний API. `provenance.txt` содержит SHA256: Core binary `09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`, source SHA и clean production checkout. Копия бинарника взята из уже проверенного предыдущим аудитом `workspace-lifecycle-evidence/proteus`, а не из меняющегося общего Cargo target. Cargo/full Rust gate не повторялся: production не менялся, все boundary-прогоны сделаны на immutable binary.

Прочие просмотренные границы: collaboration явно отклоняет worktree roles, а не молча игнорирует isolation; failed/errored/cancelled TaskTool finalization намеренно сохраняет checkout; история idle pool может истечь по cap/reuse и это заявленная process-resident семантика. Эти проверки исходников не выдаются за новые находки. Cleanup error→resume failure и потеря map при pre-dispatch Err не пересчитаны повторно.
