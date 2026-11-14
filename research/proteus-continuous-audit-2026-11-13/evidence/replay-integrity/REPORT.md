# Replay: неверное восстановление capabilities даёт ложные красные и зелёные результаты

## Зафиксированная версия

- Repository: Proteus-harness/Proteus-core.
- Исследован commit `89997df995df7c39b713e16aba216ecb19c8f497`.
- `origin/main` повторно проверен через `git ls-remote` и совпал с этим SHA.
- Рабочая копия отдельная. Production-код не изменялся, PR/публикаций нет.
- Приоритет: P2, нарушение достоверности workflow replay, а не подтверждённая потеря пользовательских данных в live runtime.

## Один корень, два подтверждённых проявления

`ReplayState::new` берёт capabilities из первого записанного запроса, а не из фактических возможностей модели (`replay_runtime.rs:95–106`). Функция `replay_capabilities` превращает конкретный `request.limits` в provider-wide верхние пределы и наличие freeform/cache/hosted fields в capability flags (`replay_runtime.rs:493–528`). Это не эквивалентные сущности.

Далее обычный `BoundModel` снова применяет `RequestShaper`. Shaper ограничивает budgets через `min` и отказывает в freeform при false capability. Эта стадия находится до replay oracle: `bound_model/hooks.rs:14`, `model_service.rs:37–41`, `shaper.rs:33–46,93–107`.

### 1. Неизменённый корректный workflow получает divergence

Синтетический valid source provider допускает до 4096 output tokens. Workflow делает два прямых model calls с per-call budgets 100 и 200. Оба source requests пропущены через настоящий `RequestShaper`; оба остаются неизменными. Journal содержит Success, оба response и итоговую history.

Тот же workflow на этом journal:

- replay первого вызова проходит;
- второй бюджет 200 заново обрезается до 100;
- `differing fields: limits`, 1/2 exchanges consumed;
- recorded Success превращается в replay Error; final history расходится.

Контроли 100 → 100 и 200 → 100: matched=true, 2/2, issues=[]. Source journal во всех случаях остаётся побайтово неизменным.

### 2. Добавленный валидный model call не обнаруживается

В source snapshot зарегистрирован разрешённый freeform tool, source capabilities поддерживают его. Два исходных запроса пока этот tool не экспонируют. Изменённый workflow выполняет прежние два вызова и затем пытается сделать третий, уже с freeform tool; полученную ошибку игнорирует, возвращая прежние output/history.

Replay ошибочно выводит `supports_freeform_tools=false`. Третий запрос отвергается shaper-ом до `consume_model_request`; никакой issue не сохраняется. Отчёт: **matched=true, issues=[], 2/2**, хотя при исходных валидных capabilities этот дополнительный запрос прошёл бы к provider adapter.

Контроль: третий обычный model call при том же игнорировании ошибки корректно отмечается как `unexpected model request #3` и matched=false.

Это особенно неприятно для regression gate: replay способен не только обвинить неизменённую реализацию, но и не заметить дополнительный live-запрос.

## Проверки

Тестовый patch добавляет только модуль `tests/audit_capabilities.rs` и его регистрацию. Полный существующий namespace `core::workflow_replay` с диагностикой: **47 passed, 2 ignored** (44 существующих + 3 диагностических теста). Два ignored tests выражают желаемые инварианты; отдельный запуск с `--ignored` даёт **2 failed, exit 101** на исходном production-коде.

Артефакты:

- `replay-suite.log`: полный focused replay suite.
- `desired-invariants.log`: два намеренно падающих regression assertions.
- `diagnostic.patch`: только тестовые изменения.
- `canonical-sessions/`: 5 синтетических исходных journals и полные JSON replay reports.
- `replay-tests`: изолированная копия собранного test executable для воспроизведения без общего Cargo lock.
- `run.sh`: фактически используемые команды, offline без model/network effects.

Runner `scripts/test.py` для `--lib` безусловно собирает весь production-module bundle. Здесь выполнен прямой focused `cargo test --offline --locked -p proteus-core --lib core::workflow_replay`: все fixtures этого namespace встроенные, внешние process-module fixtures не нужны. Это не full workspace gate, не provider dogfood и не проверка исправления.

## Направление исправления

Нужно не выдавать первый request за описание модели. Надёжный вариант: сохранять точные per-model capabilities как отдельный факт исполнения/в snapshot и использовать их в replay, включая динамический выбор модели. Объединение flags всех запросов и максимум budgets устраняет лишь часть ложных отказов, но всё ещё не восстанавливает исходные capabilities и не решает общую проблему нового валидного запроса, не представленного в source script. На этой границе важно не объявлять matched=true после искусственно сгенерированного replay-only отказа, который workflow подавил.

## Ограничения

Доказательство использует синтетический валидный journal, настоящие SessionStore, RequestShaper, BoundModel и публичный `replay_workflow`, без реальных model adapters/tools. Не утверждается, что каждый поставляемый профиль меняет budgets или freeform surface таким образом. Аналогичные проблемы с cache hints, hosted tool capabilities, reasoning и несколькими ModelRef видны по коду, но отдельно не воспроизведены и не считаются дополнительными findings.

Прежний дефект переписывания literal hook output, совпавшего с call_id, не включён повторно.
