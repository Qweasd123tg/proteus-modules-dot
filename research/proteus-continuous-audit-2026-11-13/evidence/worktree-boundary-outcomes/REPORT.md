# Новые границы результатов worktree-задач

## Версия, метод и счёт

Core remote `main`: `89997df995df7c39b713e16aba216ecb19c8f497` (повторная сверка в `remote-head.txt`).
Неизменённый production binary SHA-256:
`09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`.
Git 2.52.0, Linux. Полные executable paths/hashes в `pass*/provenance.txt`.

20 итоговых реальных root→child stdio прогонов: 10 сценариев дважды в новых
синтетических Git-репозиториях. Работают настоящие TaskTool, ToolOrchestrator,
ProcessAgentControl, дочерний `proteus server stdio` и Git. Только поведение
workflow синтетическое и детерминированное: записать файл, выполнить явно
оговорённые локальные Git-команды либо не менять ничего. Fake model binding
нужен для валидного профиля, live модель не вызывается. `max_depth=1`.

Production source не менялся. Нет PR, push, публикации, доступа к реальным
пользовательским репозиториям или секретам. Это regression evidence, не fix.

## 1. Независимый P2: создание worktree затирает существующий Git exclude

### Минимальное условие

Файл `.git/info/exclude` содержит обычный ASCII ignore-pattern, но хотя бы один
не-UTF-8 байт, например Latin-1 `é` в **комментарии**, а не в самом правиле:

```text
# private local ignores; café
local-settings.txt
```

В fixture Git корректно применяет это правило: `git check-ignore -v local-settings.txt`
возвращает 0, обычный `git status --porcelain` пуст. `local-settings.txt` содержит
только явно синтетические данные.

### Реальный outcome

После одного успешного no-op `task` с `isolation="worktree"`:
- исходные bytes exclude полностью потеряны;
- всё содержимое файла теперь ровно `/.proteus/\n`;
- `git check-ignore` возвращает 1;
- в корневом пользовательском checkout появляется `?? local-settings.txt`;
- child и parent сообщают success, предупреждения о разрушении правил нет.

Дефект возникает при **подготовке**, не при cleanup; не нужны branch switch,
nesting, resume, отмена, гонка или скрытие новых файлов настройкой status.
Он затрагивает общий Git config родительского репозитория даже если child ничего не сделал.
Контроль с тем же комментарием в UTF-8 сохраняет все исходные bytes и просто
добавляет `/.proteus/`: ignore продолжает работать. Оба исхода повторены дважды.

### Причина и минимальное направление исправления

[`workspace.rs:163-175`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L163-L175):
`fs::read_to_string(&exclude).unwrap_or_default()` трактует любую ошибку чтения,
включая encoding error, как отсутствие файла. Затем `fs::write` заменяет
существующий файл. Git в проверенном сценарии не требует UTF-8 в комментарии.

Сохранять произвольные существующие bytes; только `NotFound` считать пустым
файлом, остальные ошибки возвращать без записи. Не использовать lossy decode
с последующей перезаписью исходных bytes. Наличие строки можно проверить как
bytes. Конкурентные пользовательские записи в exclude этим опытом не проверены.

**Граница:** это потеря локальной конфигурации и снятие правил игнорирования,
не доказанная утечка. Автоматический `git add`, commit или отправка настроек
никуда не выполнялись. Распространённость legacy encoding неизвестна.

## 2. Обычная uncommitted-работа: инструкция merge не переносит результат

Без смены ветки, специальных Git flags или необычного config child изменяет
tracked `base.py`, но не коммитит. Повторены отдельно unstaged и staged варианты.

Facade честно сохраняет checkout, но добавляет:

```text
The subagent's changes live only on that branch. Review and merge it yourself, then remove the worktree.
```

Рекомендованная ветка содержит старый файл. `git merge --ff-only` этой ветки
успешно отвечает `Already up to date.`; корневой файл остаётся старым, новая
реализация есть только в сохранном child checkout/index. При контрольном
commit в исходную ветку тот же merge действительно переносит реализацию.

Это более простой regression неверного integration-note, чем уже известный
branch-switch сценарий; **не считать ещё одним независимым P1**.
`configs/prompts/codex-coder.md:7` предпочитает commit, но явно допускает
сохраняющиеся uncommitted changes, так что такой outcome не является
недопустимым только из-за отсутствия commit.

[`workspace_lifecycle.rs:211-228`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L211-L228)
не различает commits и рабочие правки. Следует явно сообщать uncommitted state
и необходимость сначала сохранить/перенести правки, а не обещать, что merge
ветки их содержит. Автоматический commit не нужен и здесь не предлагается.

**Нет доказанной потери данных:** обычный `git worktree remove` в обоих dirty
вариантах отказал с 128 и сохранил результат. `--force` не использовался.

## 3. Подтверждённое смещение cwd, с условной оценкой

Parent запущен с `--cwd <repo>/service`. В репозитории есть два разных файла:
`base.py` и `service/base.py`. Workflow исполняет одинаковый относительный edit
`base.py` в предоставленном `AgentTask.cwd`.

- Без isolation child получает `<repo>/service` и меняет `service/base.py`.
- С worktree isolation child получает **корень** нового checkout, не его
  `service/`, и меняет верхнеуровневый `base.py`. `service/base.py` остаётся старым.
- Исходный root checkout в isolated варианте не тронут.

Причина: [`workspace_lifecycle.rs:170-178`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/task/workspace_lifecycle.rs#L170-L178)
отбрасывает repo-relative prefix родительского cwd. В DTO ребёнка остаются
только новый cwd и prompt, исходный prefix отдельно не передаётся.

**Не объявляется доказанным нарушением обещанного контракта:** документация
описывает отдельный worktree, но явно не обещает сохранение subdirectory cwd.
Это воспроизводимый риск wrong-target edit в monorepo при относительном
задании, а не доказательство того, что live модель обязательно ошибётся.
Нужно выбрать semantics: сохранять prefix либо явно раскрывать смену scope в
родительской/дочерней спецификации. Отдельный P1 за это не заявляется.

## 4. Дополнение к unsafe-cleanup: index flags, но не обычный sparse checkout

Подробности в `INDEX_FLAGS.md`. В четырёх real-peer сценариях вручную выставленные
`assume-unchanged` / `skip-worktree` скрывают tracked edit даже от `status -uall`;
TaskTool после success удаляет файл и checkout как «no changes». Два реальных
контроля с обычным inherited sparse checkout сохранили появившийся файл.
Это уточнение границы уже известного cleanup family, не новая независимая P1.

## Повтор и файлы

```sh
python3 run.py --modes unstaged staged committed cwd-subdir cwd-shared exclude-utf8 exclude-legacy index-assume index-skip index-sparse --output pass1
python3 run.py --modes unstaged staged committed cwd-subdir cwd-shared exclude-utf8 exclude-legacy index-assume index-skip index-sparse --output pass2
python3 verify.py
```

Runner принимает `PROTEUS_BINARY` и `PROTEUS_REFERENCE_MODULE` для других
окружений. Каждый сценарий создаёт отдельные HOME/config/session/репозиторий
в tempdir; не меняет пользовательский Git config. `pass1/`, `pass2/` содержат
raw outputs, markers, stderr, summaries. `verify.py --expected-safe exclude`
и `integration` намеренно красные на baseline; `cwd` проверяет **условный**
желаемый инвариант, а не уже установленный контракт. `index-flags` проверяет
сохранность изменённого tracked файла и также намеренно красный.

`development/` хранит раннюю отладку harness и не является итоговым evidence.
Полный Rust gate, live provider/model и UI не запускались. Исправления не сделаны.
