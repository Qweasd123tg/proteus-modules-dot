# Proteus: практический аудит и межкомпонентные цепочки, 12–13 ноября 2026

Продолжение [статического аудита 7 ноября](../proteus-full-audit-2026-11-07/README.md) после PR #84. Здесь собраны **95 завершённых наборов проверок**, а не 95 независимых ошибок: отдельные наборы содержат несколько находок, контроли, уточнения и повторные проверки одной причины.

Публикация сохраняет отчёты, тестовые воспроизводители, исходные excerpts/patches, результаты и ограничения. **Production-исправления в этом PR не применяются.** Наличие candidate patch рядом с probe не означает готового исправления или слияния в upstream.

## С чего начать

- **Сохранность worktree:** [удаление dirty descendant](evidence/workspace-lifecycle/REPORT.md), [скрытые untracked files](evidence/worktree-hidden-files/REPORT.md), [background lifetime](evidence/nested-lifetime/REPORT.md), [память внутри временного worktree](evidence/memory-workspace-lifetime/REPORT.md). Условия различаются: вложенность, Git-настройки, путь хранения. Это не утверждение, что любая обычная задача теряет данные.
- **Жизненный цикл процессов:** [role timeout оставляет descendants](evidence/peer-tree-lifecycle/REPORT.md), [ReloadTools меняет адресата старого shell handle](evidence/component-reload/SHELL_REPORT.md), [single-instance MCP после Save](evidence/mcp-exclusive-reload/REPORT.md).
- **Профиль и восстановление:** [Save сохраняет невалидный slot](evidence/config-validation/REPORT.md), [потеря параллельной правки](evidence/config-race/REPORT.md), [Core restart и старые чаты](evidence/reconnect-state/REPORT.md).
- **Модель, workflow и контекст:** [отмена и unmatched tool](evidence/workflow-cancel/REPORT.md), [потеря BeforeStop reason](evidence/workflow-continuation/REPORT.md), [смешивание ответов subagents после output budget](evidence/completion-budget/REPORT.md). В частности, дефект continuation не воспроизвёлся в default `coding.codex_loop`.
- **Оценка harness:** [ошибки accounting](evidence/testing-fidelity/REPORT.md) и отдельно [проверка опубликованного сравнения Pi / Proteus Pi](evidence/testing-fidelity/COMPARISON_CHECK.md). Все пять строк выбранной clean-таблицы имеют **9/9 PASS**. Найденные ошибки измерителя сами по себе не опровергают эти исторические числа.
- Полный тематический индекс ниже; взаимосвязи и повторные причины в [RELATED.md](RELATED.md), условия повторения в [REPRODUCING.md](REPRODUCING.md).

## Версии и значение статуса

Перед публикацией повторно прочитаны удалённые `main` всех четырёх upstream:

| Компонент | Проверенный HEAD |
|---|---|
| Core | [`89997df995df7c39b713e16aba216ecb19c8f497`](https://github.com/Proteus-harness/Proteus-core/commit/89997df995df7c39b713e16aba216ecb19c8f497) |
| Modules | [`3270dc0f894eaf4d0360306052b806099b8f5351`](https://github.com/Proteus-harness/Proteus-modules/commit/3270dc0f894eaf4d0360306052b806099b8f5351) |
| Desktop | [`75bf201764278eac4b50d156650edcf1429101ff`](https://github.com/Proteus-harness/Proteus-desktop/commit/75bf201764278eac4b50d156650edcf1429101ff) |
| Extensions | [`4df3d0f7c168aa2947a5b014cf02f92984499d3f`](https://github.com/Proteus-harness/Proteus-desktop-extensions/commit/4df3d0f7c168aa2947a5b014cf02f92984499d3f) |

Эти HEAD совпадают с поздними аудитами. Каждый конкретный отчёт сохраняет **свою** базу, pinned зависимости и способ проверки; ранние версии нельзя автоматически приравнивать к поздним. [SOURCES.json](SOURCES.json) фиксирует проверку refs. При будущих изменениях upstream сначала сверяйте затронутый код и повторяйте нужный сценарий.

«Подтверждено» означает ровно уровень доказательства в отчёте: настоящий runtime/process, локальный fake-provider HTTP, exact-source headless projection или статическая цепочка. Эти уровни не взаимозаменяемы. Live LLM, полный native GUI и единая portable-сборка всего продукта **не проверялись** этой публикацией. Частота гонок в реальном GUI по детерминированным probes не измерена.

В базовом прогоне Core было 722 passed / 4 ignored, CLI 50 passed. Restricted integration проверки отдельно упёрлись в `NETLINK_ROUTE: Operation not permitted`; это ограничение среды, не доказательство продуктового дефекта. [Исходная сводка](evidence/practical-baseline/practical-summary.txt).

Красные regression/desired-invariant тесты часто специально демонстрируют ещё не исправленный дефект. Зелёный observational test означает, что наблюдение воспроизведено, а не что ошибка устранена. Условные интероперабельные сценарии и refuted hypotheses сохранены как таковые.

## Полный индекс

### Базовые прогоны

- [Proteus: дополнительные практические проверки, 12 ноября 2026](evidence/practical-baseline/practical-summary.txt) (`practical-baseline`).

### Git, worktrees и сохранность результатов

- [Дополнительные границы nested task/worktree lifetime](evidence/nested-lifetime/REPORT.md) (`nested-lifetime`).
- [Nested task worktrees: successful ancestor cleanup deletes a retained descendant](evidence/workspace-lifecycle/REPORT.md) (`workspace-lifecycle`).
- [P1: `status.showUntrackedFiles=no` уничтожает новые исходники worktree-задачи](evidence/worktree-hidden-files/REPORT.md) (`worktree-hidden-files`).
- [P2: task сообщает старую ветку вместо ветки с commit ребёнка](evidence/worktree-branch/REPORT.md) (`worktree-branch`).
- [Долговременная память и временный worktree: подтверждённый lifetime-конфликт](evidence/memory-workspace-lifetime/REPORT.md) (`memory-workspace-lifetime`).
- [Новые границы результатов worktree-задач](evidence/worktree-boundary-outcomes/REPORT.md) (`worktree-boundary-outcomes`).
- [Git scope и незавершённая подготовка worktree](evidence/git-scope/REPORT.md) (`git-scope`).
- [Task/worktree: неверная идентичность репозитория из-за trim пути](evidence/git-path-identity/REPORT.md) (`git-path-identity`).

### Runtime, задачи, отмена и workflows

- [Proteus Core: cancellation race review](evidence/initial-runtime/README.md) (`initial-runtime`).
- [Core: продолжение функционального аудита](evidence/round3-core/REPORT.md) (`round3-core`).
- [Proteus cross-repository functional contract review](evidence/round3-framing/REPORT.md) (`round3-framing`).
- [Proteus runtime state linkage audit](evidence/runtime-state/README.md) (`runtime-state`).
- [Core: ACP/CLI → runtime/profile/workflow boundaries](evidence/acp-cli/REPORT.md) (`acp-cli`).
- [Interactive CLI background questions and shutdown lifecycle](evidence/cli-terminal/REPORT.md) (`cli-terminal`).
- [Hook scheduling and hook replay audit](evidence/hooks-replay/REPORT.md) (`hooks-replay`).
- [Replay: неверное восстановление capabilities даёт ложные красные и зелёные результаты](evidence/replay-integrity/REPORT.md) (`replay-integrity`).
- [Proteus: nested background lifecycle and event attribution](evidence/background-agents/README.md) (`background-agents`).
- [Tool response lifecycle audit, 2026-11-13](evidence/tool-response/findings.md) (`tool-response`).
- [ReloadTools уничтожает возможность продолжения завершившегося subagent](evidence/component-reload/REPORT.md) (`component-reload`).
- [Task/worktree resume: transient admission failure destroys facade binding](evidence/command-workflows/REPORT.md) (`command-workflows`).
- [P2: task скрывает timeout дочернего агента от родительской модели](evidence/task-terminal-status/REPORT.md) (`task-terminal-status`).
- [BeforeModel consumes a model deadline that cannot interrupt it](evidence/hook-deadline/REPORT.md) (`hook-deadline`).
- [Proteus: уточнение пользователя ломает финальный checkpoint plan/execute/review](evidence/workflow-steering/REPORT.md) (`workflow-steering`).
- [Отмена tool блокирует следующие turns в single_loop и plan_execute_review](evidence/workflow-cancel/REPORT.md) (`workflow-cancel`).
- [Workflow completion review: причина продолжения теряется до модели](evidence/workflow-continuation/REPORT.md) (`workflow-continuation`).
- [Role timeout оставляет процессы субагента работающими после `timed_out`](evidence/peer-tree-lifecycle/REPORT.md) (`peer-tree-lifecycle`).

### Профили, история и persistence

- [Proteus persistence / recovery audit](evidence/initial-persistence/REPORT.md) (`initial-persistence`).
- [Proteus Core: новый функциональный проход, round 4](evidence/round4-core/REPORT.md) (`round4-core`).
- [Proteus: profile / installation / recovery trace](evidence/state-install/REPORT.md) (`state-install`).
- [История, события и UI: coherence ревизий](evidence/history-events/REPORT.md) (`history-events`).
- [Proteus: profile publication and recovery, continued audit](evidence/profile-recovery/REPORT.md) (`profile-recovery`).
- [Proteus: round 9, cold resume and user-data integrity](evidence/resume-integrity/REPORT.md) (`resume-integrity`).
- [JSONL memory: failed partial append poisons later successful memories across reload](evidence/memory-reload/REPORT.md) (`memory-reload`).
- [Proteus: профили, component update и история настроек](evidence/settings-lifecycle/REPORT.md) (`settings-lifecycle`).
- [Proteus: опубликованный профиль расходится с launch-time сервисами](evidence/profile-runtime/REPORT.md) (`profile-runtime`).
- [Proteus: потеря внешней правки профиля во время частичного Save](evidence/config-race/REPORT.md) (`config-race`).
- [Proteus Core: успешный Save записывает профиль, который больше нельзя загрузить](evidence/config-validation/REPORT.md) (`config-validation`).

### Контекст, skills, память и budgets

- [Context, interrupted tools, and memory retrieval: confirmed findings](evidence/context-memory/REPORT.md) (`context-memory`).
- [P2: отключённый локальный skill блокирует context и исправные skills](evidence/disabled-skills/REPORT.md) (`disabled-skills`).
- [P2: добавление корректных skills молча убирает весь каталог из context](evidence/skills-budget/REPORT.md) (`skills-budget`).
- [P2: лимиты tool output не ограничивают фактический текст для модели](evidence/context-budget/REPORT.md) (`context-budget`).
- [BeforeModel instructions are missing from usage telemetry](evidence/hook-usage/REPORT.md) (`hook-usage`).
- [P2: output budget склеивает отчёты разных субагентов внутри успешного wait_agent](evidence/completion-budget/REPORT.md) (`completion-budget`).

### Model adapters и wire contracts

- [Proteus model adapters: serializer and streaming review](evidence/round3-models/REPORT.md) (`round3-models`).
- [Native Anthropic errors break two recovery paths](evidence/model-context/REPORT.md) (`model-context`).
- [Context-window stop becomes a generic length error and repeats paid work](evidence/context-stop/REPORT.md) (`context-stop`).
- [Supplemental robustness probe: partially omitted Responses terminal output](evidence/usage-terminal/REPORT.md) (`usage-terminal`).

### Инструменты, файлы и LSP

- [Proteus Modules focused review](evidence/initial-modules/REPORT.md) (`initial-modules`).
- [Proteus Modules: функциональный аудит, проход 4](evidence/round4-lsp/REPORT.md) (`round4-lsp`).
- [Tools/workspace integration audit, 2026-11-13](evidence/tools-integration/REPORT.md) (`tools-integration`).

### Desktop, пользовательские сценарии и восстановление

- [Focused Desktop behaviour audit](evidence/initial-desktop/REPORT.md) (`initial-desktop`).
- [Proteus Desktop: второй построчный проход, 2026-11-12](evidence/round2-desktop/REPORT.md) (`round2-desktop`).
- [Proteus Desktop: аудит 3, новые участки](evidence/round3-desktop/REPORT.md) (`round3-desktop`).
- [Desktop audit round 4: settings and live transcript](evidence/round4-desktop/REPORT.md) (`round4-desktop`).
- [Desktop user workflow / profile inheritance audit](evidence/new-chat/REPORT.md) (`new-chat`).
- [Desktop projection, pass 8](evidence/round8-desktop/REPORT.md) (`round8-desktop`).
- [Settings Reload × Save: новый межкомпонентный дефект](evidence/desktop-settings/REPORT.md) (`desktop-settings`).
- [Desktop UX audit round 5: navigation and pane persistence](evidence/desktop-layout/REPORT.md) (`desktop-layout`).
- [Proteus Desktop: keyboard/accessibility and composed-widget audit](evidence/desktop-keyboard/REPORT.md) (`desktop-keyboard`).
- [Proteus Desktop: input echo race and retained field composition](evidence/desktop-input/REPORT.md) (`desktop-input`).
- [Proteus Desktop: незавершённые операции при переносе окна и выходе Core](evidence/project-state-lifecycle/REPORT.md) (`project-state-lifecycle`).
- [Desktop: старые чаты и потерянное уведомление о выходе Core](evidence/reconnect-state/REPORT.md) (`reconnect-state`).
- [Proteus Desktop: project catalog lifecycle and session-list focus](evidence/project-navigation/REPORT.md) (`project-navigation`).

### Extensions, Files, Git и SDK

- [Proteus Extensions / SDK / IPC audit, 2026-11-12](evidence/initial-protocol/report.txt) (`initial-protocol`).
- [Proteus Desktop Extensions: продолжение построчного аудита](evidence/round2-extensions/REPORT.md) (`round2-extensions`).
- [Extensions: продолжение построчного аудита, раунд 3](evidence/round3-extensions/REPORT.md) (`round3-extensions`).
- [Proteus: согласованность состояния Git UI между views и hash aliases](evidence/git-view-state/REPORT.md) (`git-view-state`).
- [Proteus: Files rename, несколько runtime и rehost](evidence/extension-multiview/REPORT.md) (`extension-multiview`).
- [Files / SDK: document-only initialization and active-document refresh](evidence/files-initialization/REPORT.md) (`files-initialization`).
- [Files: видимый split-документ ошибочно приравнен к скрытому](evidence/document-refresh/REPORT.md) (`document-refresh`).
- [Proteus Files: обновление дерева после Expand All и временной ошибки](evidence/files-recovery/REPORT.md) (`files-recovery`).
- [Files / SDK: активность другой сессии отменяет периодическое обновление](evidence/files-poll-starvation/REPORT.md) (`files-poll-starvation`).
- [Proteus: ошибка runtime переживает явное выключение/включение расширения](evidence/recovery-ui/REPORT.md) (`recovery-ui`).
- [Proteus extension lifecycle: late session and late workspace](evidence/extension-lifecycle/REPORT.md) (`extension-lifecycle`).
- [Proteus: действие из старого дерева панели исполняется в новой сессии](evidence/extension-action-route/REPORT.md) (`extension-action-route`).
- [Proteus: переключение чатов стирает незавершённый commit message Git](evidence/extension-context-transition/REPORT.md) (`extension-context-transition`).
- [Proteus Git: две новые границы сохранности amend-message](evidence/git-draft-safety/REPORT.md) (`git-draft-safety`).

### MCP и настройки каталога

- [MCP catalog: обычное включение сервера блокирует обновление и удаление из каталога](evidence/catalog-mcp-toggle/REPORT.md) (`catalog-mcp-toggle`).
- [MCP: ошибка схемы одного сервера блокирует весь cold launch](evidence/mcp-schema/REPORT.md) (`mcp-schema`).
- [MCP: посимвольное переименование меняет переключатели двух серверов](evidence/mcp-rename/REPORT.md) (`mcp-rename`).
- [MCP settings: добавление аргумента меняет уже существующие argv и env](evidence/mcp-text-roundtrip/REPORT.md) (`mcp-text-roundtrip`).
- [Здоровый single-instance MCP теряется после несвязанного Save или ReloadTools](evidence/mcp-exclusive-reload/REPORT.md) (`mcp-exclusive-reload`).

### Сборка, установка и обновления

- [Дополнительный аудит установки, упаковки и build/update flow](evidence/round4-install/REPORT.md) (`round4-install`).
- [Proteus: упаковка и переносимость, дополнительный проход](evidence/packaging-portability/REPORT.md) (`packaging-portability`).
- [Proteus: установка, snapshot и относительные пути](evidence/build-portability/REPORT.md) (`build-portability`).
- [Proteus: согласованность выборочных установок](evidence/install-consistency/REPORT.md) (`install-consistency`).
- [Proteus: профили установки и потерянное выборочное обновление](evidence/release-manifests/REPORT.md) (`release-manifests`).
- [CLI install → Desktop catalog: установленный модуль ошибочно регистрируется заново](evidence/component-deployment/REPORT.md) (`component-deployment`).

### Harness, benchmark и измерения

- [Benchmark design audit: oracle validity and paired conditions](evidence/benchmark-design/REPORT.md) (`benchmark-design`).
- [Audit: coding-harness outcome and usage fidelity](evidence/testing-fidelity/REPORT.md) (`testing-fidelity`).
- [Benchmark-scenarios follow-up](evidence/benchmark-cpu/REPORT.md) (`benchmark-cpu`).
- [Benchmark execution/provenance audit](evidence/benchmark-execution/REPORT.md) (`benchmark-execution`).
- [Benchmark reproducibility: stale OpenCode continuation snapshot](evidence/benchmark-reproducibility/REPORT.md) (`benchmark-reproducibility`).
- [Benchmark metrics durability: Ctrl+C and partial native export](evidence/metrics-durability/REPORT.md) (`metrics-durability`).

## Состав и проверка поставки

- Один канонический каталог на набор; повторные ZIP и старые PDF/DOCX из PR #84 не копируются. Исторические addenda объединены с исходным набором.
- [MANIFEST.json](MANIFEST.json) содержит происхождение из ранее подготовленного evidence-пакета, SHA-256 каждого файла, оригинальную длину, полный список исключений и checksum архива-источника.
- 1386 вложенных и крупных JSON/JSONL fixtures и журнальных файлов объединены в 33 deterministic `RAW_DATA.tar.gz` без потери данных; остальные 2587 evidence-файлов доступны напрямую. `restore_evidence.py` проверяет оба checksum и материализует их в **новую** папку; он ничего не запускает. Отчёты, компактные сводки, исходники и logs читаются прямо на GitHub.
- Бинарники программ, build targets, SQLite read caches, Python caches, иконный cache и дублирующие ZIP исключены. Удалённые cache-файлы регенерируются сценарием; их отсутствие не выдаётся за полный архив raw runtime directory.
- Базовые исходники и унаследованные license notices не перелицензируются MIT-лицензией delivery-репозитория. См. [LICENSE-NOTES.md](LICENSE-NOTES.md).
- [VALIDATION.md](VALIDATION.md) различает проверку поставки и историческое выполнение probes. Массового повторного запуска или дорогостоящей сборки при публикации нет.

Фразы «не опубликовано» и «исходники не менялись» внутри оригинальных отчётов описывают момент аудита. Этот каталог является последующей публикацией доказательств по просьбе владельца, без изменения production upstream.
