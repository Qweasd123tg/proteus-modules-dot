# Proteus Core: новый функциональный проход, round 4

Дата: 2026-11-13. Репозиторий: https://github.com/Proteus-harness/Proteus-core

Актуальный `main` повторно сверён с GitHub перед и после работы: `89997df995df7c39b713e16aba216ecb19c8f497`.
Изолированная рабочая копия: `/workspace/shared/core-round4-acp`. Production-код не изменён: diff содержит только две новые функции regression-тестов, одна добавлена в `#[cfg(test)]` модуль workspace.rs. Коммитов, push, PR и изменений основной рабочей копии нет.

## 1. P2: одна временная ошибка подготовки навсегда блокирует автоматическое применение того же профиля

В watcher при ошибке `refresh()` сохраняется `failed = Some(expected)`. После этого совпадающий fingerprint пропускается без срока повторной попытки, даже когда ограниченная по возрасту semantic scan снова успешно прочитала валидный профиль. Fingerprint включает сериализованный config и plugin metadata, но не доступность/работоспособность component executable. Ошибка могла быть временной: компонент ещё не установлен по новому пути, процесс не стартовал во время замены бинаря и т.п.

Изолированный тест запускает настоящий app-server с официальной reference module, затем реальный watcher с управляемым временем. Config переключается на новый, пока отсутствующий путь executable. Первая подготовка ожидаемо даёт ENOENT. После создания ссылки на уже готовую fixture **та же самая** `prepare_assembly` проходит успешно. Однако ещё четыре настоящих semantic scan watcher не делают ни одной попытки refresh, epoch остаётся прежним и `/addons.reload_error` остаётся устаревшим.

```
initial replacement failure=Some("No such file or directory (os error 2)")
after dependency recovered: retry_attempts=0,
epoch_before=ModuleEpoch(0), epoch_after=ModuleEpoch(0),
stale_error=Some("No such file or directory (os error 2)")
```

Источник:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L131-L157
- Fingerprint: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/profile_watch.rs#L30-L43
- Заявленное автоподхватывание component launch/config и сообщение о восстановлении: https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/docs/guides/configuration.md#L1477-L1492

Рекомендация: сохранять дедупликацию сообщений об ошибке, но повторять подготовку по ограниченному backoff либо отслеживать восстановление внешних зависимостей; не использовать failed fingerprint как бессрочный запрет. Перезапуск сессии, явный reload или реальное семантическое изменение config являются обходами. Изменение только комментария fingerprint не меняет. Явный reload здесь отдельно не прогонялся, его обход cache виден по коду `profile.rs`.

Тест: `repro_round4_profile_retries_after_component_dependency_recovers`.

## 2. P3: git worktree не создаётся в корректном пути репозитория с конечным пробелом

`run_git` применяет `.trim()` ко всему stdout. `create_worktree` использует результат `git rev-parse --show-toplevel` как путь, поэтому значимый конечный пробел удаляется. Следующая команда запускается уже не в исходном каталоге. В тесте создан отдельный временный git repo с пустым initial commit, расположенный в `repo with trailing space `, после чего вызван настоящий `create_worktree`.

```
root="/tmp/.../repo with trailing space "
result=Err(subagent worktree requires at least one commit
  git rev-parse HEAD failed: fatal: cannot change to
  '/tmp/.../repo with trailing space': No such file or directory)
```

Это не отсутствие initial commit: он создан до вызова. Ошибка только в преобразовании пути. Подтверждённый эффект ограничен отказом создания; вариант с существующим соседним repo по обрезанному пути не воспроизводился и не заявляется как отдельный подтверждённый эффект.

Источник:
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L26-L33
- https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/agent_control/workspace.rs#L180-L194

Рекомендация: отделить чтение путей от общих текстовых результатов git; удалять только завершающий разделитель строки, не произвольные пробельные символы.

Тест: `repro_round4_worktree_preserves_significant_trailing_space_in_root`.

## Проверки

Штатные targeted tests: **61 passed, 0 failed**:
- ACP: 5;
- agent-control workspace: 11;
- task/workspace lifecycle: 16;
- profile watcher: 3;
- session selection: 9;
- turn progress: 13;
- context map: 4.

Два новых regression-теста дают ожидаемые падения. Оба повторены ещё три раза с тем же результатом. `git diff --check` чистый. Предварительный compile-initial.log содержит две ошибки сборки самого нового теста (private field и Display): исправлены до воспроизведения, это не продуктовые дефекты.

Для воспроизведения: применить `repros.patch` к указанному SHA, указать готовую официальную fixture через `PROTEUS_TEST_REFERENCE_MODULE`, затем:

```
cargo test --locked -p proteus-core --lib repro_round4 -- --nocapture
```

Никаких реальных аккаунтов, live model API, платных запросов, внешних процессов из недоверенного пакета нет. Использованы готовая официальная fixture из прошлого прохода, системный git и временные каталоги.

## Точный охват и ограничения

`coverage.tsv`: **30 файлов целиком, 5307 строк**; дополнительно восемь файлов прочитаны частично с точными диапазонами, два документальных диапазона. Повторно прочитанные старые workflow/runtime участки не прибавлены к новому полному охвату.

Основные новые участки: ACP lifecycle/input/event projection/config, CLI init, worktree lifecycle, task facade/spec, collaboration reservations/messages, process summary/output bounds, context-map telemetry, turn-progress projection, profile reload/recovery и сохранение model-selection.

В ACP новых подтверждённых ошибок не обнаружено. Не объявлены находками: fallback text после commentary без доказанного нарушающего workflow; context telemetry при отсутствии session_id (все проверенные production callers передают Some); подозрение на повторные progress deltas без реального producer.

Это не полный репозиторный аудит. Не запускались полный workspace gate, браузерный/редакторский ACP E2E, live-модели, Windows/macOS. Предыдущие cancel/storage/steering находки не повторялись. Автоматические security probes не использовались.

Артефакты: `repros.patch`, `repro.log`, `repro-repeat-{1,2,3}.log`, семь `test-*.log`, `coverage.tsv`, этот отчёт.
