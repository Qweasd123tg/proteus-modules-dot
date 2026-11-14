# Отмена tool блокирует следующие turns в single_loop и plan_execute_review

## Новая подтверждённая проблема

**P2, высокая уверенность.** После отмены во время выполнения tool workflows `coding.single_loop` и `coding.plan_execute_review` отправляют следующий запрос с сохранённым `ToolCall`, но без соответствующего `ToolResult`. Повторное обычное сообщение и полный перезапуск с cold resume не исправляют запрос. Native Anthropic adapter сериализует этот незакрытый вызов в `tool_use` без `tool_result`.

Это не прежняя проблема «compaction сохраняет orphan aborted result»: здесь **compaction вообще не подключён**, а отсутствует результат при сохранённом вызове. Отдельно от steering/private-draft проблемы: нет steering, приватного anchor или ошибок checkpoint.

## Версии и границы

- Core `89997df995df7c39b713e16aba216ecb19c8f497`, Modules `3270dc0f894eaf4d0360306052b806099b8f5351`. Удалённые HEAD повторно проверены 2026-11-13; `remote-heads.log`.
- Неизменённые ранее собранные Core, coding-workflow и reference-module. Хеши `provenance.json` совпадают с provenance предыдущего workflow/steering исследования. Reference-module собран из Modules на указанном SHA; production-исходники в этом проходе не менялись.
- Настоящие Core stdio app-server, workflow process, policy/context, read-only tool process, journal, native Anthropic adapter и HTTP transport.
- Модель — только локальный HTTP fixture на `127.0.0.1` с синтетическим ключом. Первый ответ детерминированно просит read-only `probe`; tool ждёт сигнала. Никакие пользовательские данные и живые LLM не используются.
- Каждый сценарий имеет отдельные временные workspace, HOME, PROTEUS_HOME и XDG paths. Отмена посылается только после фактического начала `probe`.
- Fixture возвращает **собственный** HTTP 400 при отсутствии результата. Это не заявление о запросе к реальному Anthropic. Сохранённые native HTTP bodies сами доказывают нарушение формата; код/текст live ошибки и её частота не измерялись.

## Поведение

Каждый сценарий повторён 3 раза, всего **18 process-прогонов**. Каждый прогон включает initial turn, два warm followup, cold resume с ещё одним followup и отдельный контроль после очистки синтетической истории.

| Workflow | Условие | Два warm followup + cold followup | После clear |
|---|---|---|---|
| `coding.single_loop` | tool завершился | 3/3 Success | Success |
| `coding.single_loop` | tool отменён | **3/3 повторения: все 3 followup Error** | Success |
| `coding.plan_execute_review` | tool завершился | 3/3 Success | Success |
| `coding.plan_execute_review` | tool отменён в plan | **3/3 повторения: все 3 followup Error** | Success |
| `coding.codex_loop` | tool завершился | 3/3 Success | Success |
| `coding.codex_loop` | tool отменён | **3/3 Success**, prompt-only `aborted` result | Success |

В каждом проблемном прогоне:
1. ToolCall `probe-1` принят и сохранён checkpoint до исполнения.
2. Отмена завершается `TurnSettled.status=canceled`; результата tool в durable checkpoint нет. Это допустимая незавершённость истории, не потеря уже полученного успешного результата.
3. Следующие **три** реальные HTTP-запроса native adapter содержат assistant `tool_use(id=probe-1)`, затем новые user texts, но нигде не содержат matching `tool_result`.
4. Локальная проверка формата отклоняет каждый из них. Добавление user text не меняет состояние; cold reopen сохраняет его.
5. После `clear_history` новый синтетический turn проходит. Очистка здесь только диагностический контроль, не рекомендуемое исправление с потерей контекста.

Всего зафиксировано **18 некорректных HTTP bodies**: 2 workflows × 3 повторения × 3 followup. В остальных ветках нет unmatched calls. `verify.py` дополнительно сверяет terminal statuses с durable journal и фактический checkpoint.

В шести предварительных model/v13 process-прогонах, без HTTP-отклонения, оба workflow принимали такие запросы и успешно отвечали через permissive fixture. Это показывает, почему обычный fake-model unit test не выявляет ошибку. Логи находятся в каталогах без префикса `native-`.

## Причинная цепочка

1. [single_loop сохраняет calls до исполнения](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/single_loop.rs#L112-L115); [plan loop делает то же](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/plan_execute_review.rs#L139-L145). После отмены выполнение не доходит до append/checkpoint результата.
2. [TurnScaffold копирует durable history в model_messages](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/scaffold.rs#L99-L121).
3. [single_loop](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/single_loop.rs#L29-L36) и [plan_execute_review](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/plan_execute_review.rs#L44-L50) сразу идут в sampling, не нормализуя незавершённые calls.
4. Контрольный [codex_loop явно добавляет prompt-only outputs](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/codex_loop.rs#L29-L38), а [normalize_missing_tool_outputs](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/codex_recovery.rs#L44-L77) помечает их `PartScope::Request`. Поэтому codex работает без изменения durable фактов об исполнении.
5. [Native Anthropic serialization](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/model/model-pack/src/adapters/anthropic/request.rs#L190-L218) сохраняет malformed историю без нормализации. Согласно [официальным требованиям формата](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls), соответствующий result обязан непосредственно следовать за tool-use сообщением. Документация повторно проверена 2026-11-13.

## Направление исправления

Добавить согласованную request-only нормализацию незавершённых calls в affected workflows, не выдавая синтетический результат за факт исполнения и не стирая durable историю. Не нужно менять общие contracts или делать provider-specific recovery в Core. Точную формулировку interrupted instructions оставить ответственностью workflow.

Регрессия должна проверять cancel → warm retry → cold retry через реальный сериализатор, а также completed-tool control. При совмещении исправления с compaction необходимо учесть уже найденный дефект переноса request-only aborted result без соответствующего call: простое копирование normalize-before-compaction недостаточно для всей комбинации.

## Проверки и ограничения

- Неизменённый ранее собранный unit target coding-workflow: **92 passed** (`baseline-workflow.log`). Это baseline на pinned build, не новая сборка или full workspace gate.
- 6 предварительных synthetic model/v13 process-сценариев.
- 18 native-HTTP process-сценариев, каждый проверяет warm/cold lifecycle; `native.py` и `native.log`.
- `python3 verify.py`: все 18 наборов доказательств прошли проверки; `verify.log`.
- Full workspace, Desktop GUI, live API, cancellation во всех фазах и другие provider adapters не проверены. Для plan_execute_review процессный cancel воспроизведён именно в plan tool phase; execute имеет аналогичный код, но отдельно не измерен.
- Ничего не опубликовано; commits, PR и push не выполнялись. Производственный патч не делался.

Повтор: заменить абсолютные пути к pinned executables в `native.py` и Core fixture import в `probe.py`, затем `python3 native.py && python3 verify.py`. Все изменения ограничены синтетическими временными сессиями и evidence-каталогом.
