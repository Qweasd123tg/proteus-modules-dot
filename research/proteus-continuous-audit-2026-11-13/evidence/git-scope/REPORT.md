# Git scope и незавершённая подготовка worktree

## Версия и метод

Core `main` повторно проверен через GitHub connector 2026-11-13 11:41 UTC:
`89997df995df7c39b713e16aba216ecb19c8f497` (`remote-head.json`).
Неизменённый production binary SHA-256:
`09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`.
Git 2.52.0, Linux; полные пути и хеши в `pass*/provenance.txt`.

11 сценариев повторены дважды в новых изолированных fixture-каталогах.
Всего **34 настоящих вызова TaskTool, 30 запусков дочернего workflow**.
В четырёх попытках ошибка подготовки намеренно не допускает child dispatch.
Работают настоящие Core stdio server, ToolOrchestrator, TaskTool,
ProcessAgentControl, process pool, MCP client и системный Git. Только workflow,
MCP server и policy являются детерминированными fixtures. Fake model binding
загружен для валидного профиля; live модели и внешние сервисы не вызываются.

Каждый сценарий имеет отдельные HOME/config/session и два синтетических Git
репозитория `requested` и `other`. Их `base.py` различается. Runner очищает
Git scope variables из своего baseline environment и вводит только явно
указанные переменные для соответствующего дочернего Core. Проверки состояния
выполняются с чистым Git environment. Production source не менялся. Нет PR,
push, merge, публикации или работы с пользовательскими репозиториями.

## 1. Новый P2: унаследованный Git environment меняет репозиторий worktree-задачи

### Минимальный и наиболее показательный сценарий

Core запущен с `--cwd <requested>`, но в его environment остался **абсолютный**
`GIT_DIR=<other>/.git`. `GIT_WORK_TREE` отсутствует. Это явное условие дефекта,
не утверждение о штатном запуске без таких переменных.

Workflow вызывает обычный `task` с `isolation="worktree"`. Child должен
изменить и закоммитить `base.py` в предоставленном ему checkout.

Наблюдается:

1. Root `AgentTask.cwd` действительно равен `<requested>`.
2. Каталог ребёнка выглядит правдоподобно:
   `<requested>/.proteus/worktrees/coder-call_0`.
3. Однако исходное содержимое файла в нём — `SOURCE = "other repository"`,
   а `.git` ссылается на common dir второго репозитория.
4. Child commit успешно создаётся в ветке `proteus/coder-call_0` **в `other`**.
5. Task сообщает success, возвращает task_id и обычную инструкцию review/merge.
   В `requested` такой ветки нет (`rev-parse --verify` возвращает 128),
   в `other` она есть, отличается от `other/main` и содержит новый файл.
6. Рабочие файлы обеих исходных main-веток не тронуты. Это подмена базы и
   местоположения результата, а не доказанная потеря исходных данных.

Итоговые raw evidence: `pass*/env-dironly-commit-{summary,outputs}.json` и
`*-markers.jsonl`. Это не старый случай «незакоммиченные изменения не входят
в merge»: здесь **commit есть**, но он принадлежит не выбранному репозиторию.

### Дополнительные варианты и контроли

- Только `GIT_DIR=<other>/.git`, без commit: та же неверная база/ветка,
  успешный resumable результат. `env-dironly`.
- `GIT_DIR=<other>/.git` + `GIT_WORK_TREE=<other>`: даже checkout размещается
  под `other`, хотя root task cwd всё ещё `requested`. `env-other`.
- Обе переменные указывают на сам `requested`: создание попадает в правильный
  репозиторий, но cleanup status/HEAD смотрят на parent вместо child.
  Затем **отдельная защита Git `worktree remove` отказывает с 128**, сохраняет
  dirty checkout, facade сообщает cleanup failure и не выдаёт task_id.
  То же происходит в `env-other`. Это дополнительный regression известной
  потери facade resume mapping при cleanup error, **не отдельный P1**.
- Полностью очищенный Git scope environment, с commit и без: база — requested,
  ветка принадлежит requested, other не затронут, normal retained task_id.
  `env-clear`, `env-clear-commit`.

**Потери данных нет ни в одном подтверждённом сценарии.** Никакие overrides
защиты Git, `--force`, скрытие untracked или index flags здесь не применялись.

### Причина и связь с существующим правильным контрактом

[`workspace.rs:26-56`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L26-L56)
строит repo root, base commit и checkout из результатов `run_git`.
[`run_git:180-194`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L180-L194)
использует только `git -C`, не убирая inherited repository overrides.
Затем [`workspace_lifecycle.rs:170-178`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L170-L178)
передаёт полученный путь как authoritative child cwd.

При этом существующий Git launcher workspace HTTP API уже явно устанавливает
противоположный инвариант: scope принадлежит session cwd, а не Git environment
сервера; он очищает `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`,
`GIT_COMMON_DIR`, `GIT_PREFIX`:
[`command.rs:54-75`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/http/workspace/git/command.rs#L54-L75).
HTTP API динамически не запускался: сравнение этого второго пути статическое;
сам неправильный task outcome воспроизведён настоящим stdio backend.

Минимальное направление: унифицировать именно правило repository-scope
при запуске Git для task creation/inspection/cleanup с существующим cwd-owned
правилом. Не копировать без разбора все HTTP flags и не отключать hooks
автоматически. Проверить оба абсолютных-env сценария, включая committed result.
Распространённость такого окружения у пользователей не оценивалась.

## 2. Новый P3 robustness: post-checkout failure оставляет неуправляемую подготовку

В synthetic repo установлен простейший доверенный `post-checkout` hook:
напечатать диагностическое сообщение и выйти с 1. Никаких сетевых действий,
внешних зависимостей или правок исходников hook не делает.

Настоящий `git worktree add -b` создаёт checkout и ветку, затем запускает hook,
а из-за его кода возвращает failure. TaskTool возвращает error
`failed to add git worktree`; child workflow **не запускался**. Уже созданные
checkout и ветка остаются, но до `WorkspaceInfo`/lifecycle ownership дело
не дошло, автоматического terminal decision для них нет.

После исправления hook (exit 0) и штатного `new_session` повтор того же
session-local call id возвращает `worktree path already exists`. Новый call id
запускается и успешно очищается, но первый orphan остаётся. Повтор ID делается
только в новой сессии, чтобы не обходить session journal duplicate-call guard.

`pass*/hook-*` фиксирует три попытки `[false, false, true]`, две разные root
session identity, ровно один child workflow и orphan в Git worktree list после
каждого шага. Root index чист; orphan скрыт обычным `/.proteus/` exclude.
Путь не полностью скрыт от пользователя: он есть в первой Git error message,
а `git worktree list` позволяет найти состояние. Поэтому это **P3**, не потеря
данных, не незаметный success и не непоправимая блокировка.

Причина: `create_worktree` возвращает `Err` до создания `WorkspaceInfo`
([`workspace.rs:41-56`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L41-L56));
`run_owned` сразу возвращает `task_error`
([`workspace_lifecycle.rs:60-64`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L60-L64)).

Направление: typed результат частично выполненной подготовки с фактическими
path/branch и владельцем cleanup/retention. Не считать любой nonzero Git exit
отсутствием effects. При rollback сначала проверить состояние и сохранить
изменения, которые мог сделать hook; безусловный remove здесь неверен.
Не подавлять failure hook и не продолжать child вопреки его ошибке.

## 3. Полезный отрицательный результат: stale MCP cwd не подтвердился

Проверена отдельная связь pool → удалённый checkout → повторное создание того
же pathname. Два допустимых разных call id (`call/0`, `call:0`) после текущего
sanitize дают одинаковое имя checkout. Первая clean task удаляет checkout;
вторая fresh task создаёт его заново. При max_idle_processes=2 Core действительно
повторно использует **тот же peer PID**, что подтверждено markers.

Но fresh-task session rotation пересоздаёт workflow и MCP процессы. MCP PID
меняется, счётчик сбрасывается до 1, оба чтения относительного `base.py` успешны.
Ошибки deleted cwd нет. Контроли с уникальными путями, отключённым idle pool и
shared cwd тоже успешны. Всего 16 successful MCP reads (4 сценария × 2 calls ×
2 повтора). **Новый баг за этот путь не заявляется.**

Предварительная попытка повторить буквально одинаковый call id в одной сессии
была штатно отвергнута journal (`requested more than once`); её raw outputs
оставлены только в `development/`, не включены в итоговый пакет/счёт.

## Проверка и воспроизведение

```sh
python3 run.py --output pass1
python3 run.py --output pass2
python3 verify.py
```

`verify.py` проверяет все наблюдённые outcomes и controls, включая неизменность
обоих main checkout, настоящий committed result в нужной/неверной Git базе,
отсутствие child dispatch в ошибках подготовки и фактическое peer reuse.

```sh
python3 verify.py --expected-safe env
python3 verify.py --expected-safe hook
```

Обе проверки желаемых безопасных инвариантов намеренно красные на baseline;
логи сохранены. Runner принимает `PROTEUS_BINARY` и
`PROTEUS_REFERENCE_MODULE` для переноса окружения. Python syntax check проходит.
Полный Rust gate, UI, live provider calls и production patch не выполнялись.
Ранние неитоговые debugging runs из `development/` не входят в evidence ZIP.
