# Task/worktree: неверная идентичность репозитория из-за trim пути

## Версия и достоверность

Core `main`: `89997df995df7c39b713e16aba216ecb19c8f497`, повторно проверен GitHub connector; точное время и URL в `remote-head.json`.
Неизменённый production binary SHA-256: `09b8d6efca263b8ddac0660c08bfca66b9bb75007e4f792ce5059c6503f6ba1f`.
Git 2.52.0, Linux. Исходный checkout Core остался чистым.

Каждый из шести сценариев повторён в новом изолированном каталоге: **12 настоящих TaskTool invocation, 10 дочерних workflow**. Core stdio server, ToolOrchestrator, task facade, ProcessAgentControl, process pool и Git настоящие. Workflow/policy детерминированные fixtures; fake model binding только делает профиль валидным, live модель не вызывается. Синтетические repositories не являются рабочими пользовательскими repos.

Все Git scope variables из прежнего GIT_DIR reproducer очищены: `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_PREFIX`. Во всех 12 summaries `git_environment == {}`. Названия сценариев `env-...` унаследованы от fixture, но в этих сценариях окружение **не переключает** repo.

## Новый условный P2: cwd с завершающим whitespace может направить задачу в соседний repo

1. Существуют два независимых репозитория: `requested ` (имя заканчивается пробелом) и `requested` (без него).
2. Core запускается с `--cwd` **`requested `**. Root workflow действительно получает точный путь с пробелом; это сохранено в `task_result.cwd`.
3. Root вызывает `task` для роли с `isolation="worktree"`.
4. `git rev-parse --show-toplevel` выводит корректное имя `requested ` плюс служебный перевод строки. Но helper `run_git()` вызывает `.trim()` и превращает его в путь **другого** repo `requested`.
5. Последующие rev-parse HEAD, изменение info/exclude, worktree add и сам child используют соседний repo.
6. Child читает `SOURCE = "other repository"`, пишет и **коммитит** результат. Task возвращает `ok=true`, `status=completed`, task_id и обычную инструкцию интеграции.
7. Ветка `proteus/coder-call_0` и новый commit есть только в соседнем repo. В указанном пользователем repo такой ветки нет. Основные файлы обоих main checkout остаются неизменными.

Это не только косметическое искажение пути или ошибка CLI: происходит реальная работа на другой базе и реальный commit в другом Git graph. Потеря исходных файлов не заявляется.

### Матрица, два повторения каждого

| Сценарий | Результат |
| --- | --- |
| Обычный `requested`, независимый `other` | Контроль: работа и commit в requested |
| `requested ` и соседний `requested` | Success, но исходники/ветка/commit в соседнем repo |
| `requested\u00a0` (NBSP) и соседний `requested` | То же |
| `requested\t` и соседний `requested` | То же |
| `requested\n` и соседний `requested` | То же |
| `requested `, без trimmed sibling | Ошибка «requires at least one commit / cannot change to ...», хотя выбранный repo имеет корректный HEAD; child не запускается |

NBSP, tab и newline здесь не независимые дефекты. Все варианты проверяют один и тот же lossy decoder. Переименования рабочей папки, смены branch, скрывающих status config и унаследованного Git env нет.

## Причина и граница исправления

- [`workspace.rs:28–35`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L28-L35): repo_root доверяется тексту `run_git`, затем используется для всех последующих операций.
- [`workspace.rs:178–194`](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L178-L194): generic helper применяет `String::from_utf8_lossy(...).trim()` ко всем stdout, включая paths.

Path output нельзя разбирать как свободный текст. Нужен отдельный path decoder, который сохраняет значимые bytes/whitespace и снимает только терминатор записи. Для pathname, заканчивающегося newline, `trim_end_matches('\n')` также недостаточно: он удалит больше одного байта. Не-UTF8 paths следует явно поддерживать или отклонять, но не silently replacement-decode; такой вариант в данном пакете **не проверялся**. Изменения production-кода не делались.

## Проверки и отрицательный результат

`python3 verify.py` проходит: обе матрицы, requested cwd, отсутствие Git env, исходные файлы, владельцы branches и commit contents проверены.
`python3 verify.py --expected-safe` падает на целевом инварианте: child checkout должен принадлежать exact requested repo. Вывод в `expected-safe.log`.

Дополнительно проверена гипотеза о потере dirty submodule при `submodule.<name>.ignore=all`. Git status действительно пустой, но `git worktree remove` отклоняет initialized submodule с кодом 128 и сохраняет файл. Это **Git-only negative control**, не дополнительные TaskTool calls; `submodule_probe.py` и `submodule-negative.json`. Новая потеря данных здесь не заявляется.

Не считаются новыми: ранее подтверждённый GIT_DIR scope leak, post-checkout partial preparation, status.showUntrackedFiles, index flags, stale branch note и nested workspace lifetime.

## Повторение

```sh
python3 run.py --output pass1
python3 run.py --output pass2
python3 verify.py
python3 verify.py --expected-safe  # ожидаемый nonzero до исправления
python3 submodule_probe.py
```

`PROTEUS_BINARY` и `PROTEUS_REFERENCE_MODULE` позволяют указать те же pinned binaries в другом workspace. Скрипт сохраняет сценарии в новых tmp directories; существующие результаты лучше писать в новые output dirs. Publication, PR, push и merge не выполнялись. Пакет содержит fixtures/reports/JSON evidence, но не binaries.
