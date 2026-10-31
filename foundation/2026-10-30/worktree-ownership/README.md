# Worktree: единый владелец и отмена перед cleanup mutations

Source-reviewed предложение для `Proteus-harness/Proteus-core` на commit
`befd30516aefa6f0a0ad5db9924ad4957160b8dc`. Полный самостоятельный patch:
`worktree-ownership.patch`, SHA-256
`38eb7954c09e8aff742f6581432f780ef539769b8585a270e40cf8b0bdf39087`.
Это замена старого предложения `90d9dc23`, а не добавка поверх него.
Terminal-result retention независим от этой правки.

## Изменение

- Resume атомарно забирает idle worktree record: второй caller не получает
  checkout и не может очистить каталог активного владельца.
- Отдельный async owner удерживает preparation, host invocation и finalization;
  Drop foreground waiter отменяет только существующий token вызова.
- Наблюдаемая отмена после dispatch, non-Completed result и непрозрачная ошибка
  сохраняют checkout. Только явный resumable result допускает возврат mapping.
- Canonical Git helper проверяет тот же token после readonly inspections,
  перед `worktree remove`, `worktree prune` и каждым `branch -d`.
- Отсутствующий/уже удалённый checkout с сохранённой веткой имеет отдельный
  outcome. Он не возвращается в resume map и не рекламирует facade task ID.
- Свежая preparation без dispatch может быть очищена несмотря на отмену;
  незапущенный resume вместо этого восстанавливает свой idle record.

Изменены три production-файла, добавлен colocated lifecycle test module,
обновлены существующие Git-helper tests и русский security/policy guide.
`SOURCES.json` связывает baseline и candidate bytes всех пяти путей.

## Проверка и ограничения

Две исходные независимые source-review и повторный bounded caller/helper review
не выявили source blocker. При восстановлении пакета повторно сверены hash patch
и пяти candidate файлов; strict forward/reverse `git apply` с
`--whitespace=error-all` восстановил точные candidate/baseline bytes. Installed
rustfmt 1.95.0 toolchain проверил четыре Rust-файла с edition 2024,
`skip_children=true`. Production, tests, fixtures, Cargo, builds и CI **не
запускались**. Это не compile/runtime evidence и не готовность к merge.

Regression sources покрывают concurrent resume, waiter drop, unsuccessful/error
retention, pre-dispatch cancellation/rollback, late-effect boundary, отсутствие
resume для branch-only результата и детерминированную отмену на границах
Git mutations. Поздний effect моделируется owned futures, не реальным broker.

Check-to-command race остаётся. Уже запущенная Git mutation не отменяется и не
откатывается; следующая проверка пропускает лишь последующие команды. Обычный
успешный Completed result, чистый Git status и cancel ACK не доказывают остановку
внешних process-tool/exec/PTY writers. Полного effect drain правка не добавляет.
Owner panic/shutdown/crash не имеют durable recovery; зависший host удерживает
owner state. Сохранённые checkout/branches требуют диска и ручного recovery.

До интеграции нужны разрешённые executable gates: Core workspace/task lifecycle
tests, реальные process-agent pool/control и policy/approval timeout/cancel
boundaries. Источники тестов не заменяют эти проверки.
