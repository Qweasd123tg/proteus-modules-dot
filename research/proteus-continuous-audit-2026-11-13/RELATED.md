# Связи и дедупликация находок

Число каталогов или заголовков не является числом независимых дефектов. Оригинальные отчёты сохраняются для проверки эволюции доказательств. Ниже указаны наиболее важные пересечения, чтобы не заводить дублирующие fixes/issues.

| Семейство | Каноническая полная проверка и уточнения |
|---|---|
| Cleanup ancestor → descendant | [workspace-lifecycle](evidence/workspace-lifecycle/REPORT.md) даёт dirty nested loss; [nested-lifetime](evidence/nested-lifetime/REPORT.md) расширяет lifetime на живого background reader; [memory-workspace-lifetime](evidence/memory-workspace-lifetime/REPORT.md) показывает память внутри того же временного дерева. Это разные условия одной cleanup-границы, не три безусловных дефекта любых worktrees. |
| Неверная clean/dirty оценка | [worktree-hidden-files](evidence/worktree-hidden-files/REPORT.md) с `status.showUntrackedFiles=no`; [index flags](evidence/worktree-boundary-outcomes/INDEX_FLAGS.md) отдельно показывает, почему одного `-uall` недостаточно для вручную скрытых tracked edits. Обычный sparse-checkout контроль не подтвердил потерю. |
| Whitespace в Git path | Ранний [round4-core](evidence/round4-core/REPORT.md) уточнён [git-path-identity](evidence/git-path-identity/REPORT.md): trim может не только сломать путь, но и направить в существующий соседний репозиторий. Не считать повтором новую root cause. |
| Выбор устаревшей сборки | [round4-install](evidence/round4-install/REPORT.md) и [packaging-portability](evidence/packaging-portability/REPORT.md) пересекаются по игнорированию `CARGO_BUILD_TARGET`; entry points и последствия различаются. |
| Anthropic overflow/recovery | [model-context](evidence/model-context/REPORT.md) проверяет классификацию error; [context-stop](evidence/context-stop/REPORT.md) отдельно расширяет это на HTTP-200 `model_context_window_exceeded` stop и потерю usage. Общая область восстановления, разные wire branches. |
| Устаревший usage export | [benchmark-reproducibility](evidence/benchmark-reproducibility/REPORT.md) и часть [metrics-durability](evidence/metrics-durability/REPORT.md) относятся к повторному использованию или блокировке fallback существующим export. Ctrl-C teardown в metrics отчёте остаётся отдельной цепочкой. |
| Вопросы и input identity | [runtime-state](evidence/runtime-state/README.md), [history-events addendum](evidence/history-events/ADDENDUM-input-and-activity.md) и [tool-response](evidence/tool-response/findings.md) проверяют разные места correlation/lifetime. Collision относится к указанным duplicate IDs; это не доказательство коллизий всех штатных уникальных вопросов. |
| Snapshot/history coherence | [history-events](evidence/history-events/REPORT.md) + два addenda опубликованы одним каталогом, а не тремя повторными пакетами. |
| Profile include/history | [state-install](evidence/state-install/REPORT.md) и [plugin-history addendum](evidence/state-install/ADDENDUM-plugin-history.md) вместе показывают сохранение/воскрешение конфигурации; не утверждают потерю всех настроек при любом Save. |
| Reload и task identity | [component-reload](evidence/component-reload/REPORT.md) рассматривает пересоздание пула; [command-workflows](evidence/command-workflows/REPORT.md) рассматривает потерю facade mapping после admission failure. Симптом resume похож, но причины и необходимые regression различаются. Shell generation вынесен в отдельный [SHELL_REPORT](evidence/component-reload/SHELL_REPORT.md). |
| Desktop recovery | [project-state-lifecycle](evidence/project-state-lifecycle/REPORT.md) описывает зависшие operation flags/route transfer; [reconnect-state](evidence/reconnect-state/REPORT.md) отдельно stale Chat Api и потерянный exit при mutex contention. Эти дефекты не объединены только по слову reconnect. |
| Git draft | [context-transition](evidence/extension-context-transition/REPORT.md) проверяет потерю draft при смене session; [git-draft-safety](evidence/git-draft-safety/REPORT.md) проверяет amend-message и смену HEAD. Сохранность формы и выбор коммита требуют разных контролей. |

## Сохранённые оговорки

- Условные interop/SDK cases не повышены до доказанных штатных end-to-end инцидентов.
- Refuted гипотезы и успешно пройденные контроли остаются в исходных отчётах, но не считаются finding.
- Нет суммарной оценки «всё сломано» или «всё исправлено». Приоритет определяется условием, эффектом и способом воспроизведения конкретного случая.
- Предыдущий аудит 7 ноября и старые source proposals остаются по прежним ссылкам; здесь нет их повторной публикации и нет автоматического переноса их статусов на новые HEAD.
