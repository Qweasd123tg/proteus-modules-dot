# Proteus: уточнение пользователя ломает финальный checkpoint plan/execute/review

## Подтверждённый новый дефект

**P2.** В `coding.plan_execute_review` обычное сообщение, отправленное во время работы, может быть успешно принято в очередь, доставлено модели, а затем превратить полностью подготовленный ответ в ошибку `workflow output dropped steering response anchor …`.

Условие: уточнение доставляется после tool round, а следующим ответом execute-фазы становится текстовый draft без нового tool call. Этот draft присутствует в model context, но отсутствует в сохраняемой истории. Core использует его как опорное сообщение для уточнения и отвергает итоговый checkpoint.

Это не прежний дефект enqueue → ошибка event sink: здесь отправка и доставка успешны, event sink не ломается. Не требуется ошибка провайдера, compaction, cancellation, reload, нестандартный workflow или сбой диска.

## Версии и способ проверки

- Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Modules: `3270dc0f894eaf4d0360306052b806099b8f5351`.
- `git ls-remote origin HEAD` обоих репозиториев повторно подтверждён 2026-11-13, см. `remote-heads.log`.
- Использованы ранее собранные неизменённые Core executable и штатные process modules на этих SHA. Хеши в `provenance.json`; исходный build provenance Core сохранён рядом. Рабочие деревья исходного Core, Modules и checkout сборки workflow чисты по tracked diff.
- Все сессии и профили созданы отдельно в `tempfile` workspace с отдельными HOME/PROTEUS_HOME/XDG-путями.
- Реальные Core stdio app-server, очередь steering, process workflow, context, policy, tool host, journal и cold resume. Модель — детерминированный локальный `model/v13` fixture. Read-only `probe` — существующий process tool fixture проекта. Он возвращает `ok`, не изменяя пользовательские файлы.
- Ни сетевые провайдеры, ни платные модели, ни реальные пользовательские проекты не использовались. Production-код не менялся; commit/push/PR не выполнялись.

## Матрица: каждый сценарий повторён три раза

| Сценарий | Последовательность | Результат |
|---|---|---|
| `plan_control` | plan tool → plan text → execute draft → review | 3/3 Success |
| `single_steering` | tool → уточнение → final, `coding.single_loop` | 3/3 Success |
| `plan_steering` | plan tool → уточнение → plan text → execute draft → review | **3/3 Error** |
| `execute_steering` | plan text → execute tool → уточнение → execute draft → review | **3/3 Error** |
| `plan_execute_tool` | plan tool → уточнение → plan text → execute tool → draft → review | 3/3 Success |

Для обоих падающих сценариев:
1. Второй `send` получает `ok=true`, `accepted=true`, `queued=true`.
2. Уточнение действительно присутствует в следующем каноническом model request.
3. Модель успешно формирует все **четыре** ответа, включая final review.
4. Финальная операция падает на `host.history.checkpoint`. `TurnSettled.status=error`.
5. Live snapshot и snapshot после полного закрытия/нового запуска Core совпадают. В обоих сохранены исходное сообщение, завершённый tool, уточнение и ошибка; итогового assistant answer в обычной conversation projection нет.
6. **Raw journal хранит модельный final response.** Это потеря нормального завершения/отображения ответа, не утверждение о безвозвратном уничтожении всех данных. Уточнение сохранено ровно один раз.

Факт дополнительного execute tool round важен: он создаёт persistent anchor и делает контрольный сценарий успешным. Ошибка зависит от связи фаз и истории, а не от самого текста уточнения.

## Причинная цепочка

1. [Core доставляет steering после tool response и привязывает его к первому сообщению следующего ответа](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/steering.rs#L444-L490).
2. [Приватный план получает новый message ID и request-scope](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/plan_execute_review.rs#L117-L137). Если уточнение впервые привязалось к плану, на execute request Core не находит старый ID и правильно переносит anchor на execute response.
3. [Execute draft, напротив, остаётся с исходным ID в `model_messages`, но добавляется в `persistent_messages` только при наличии tool calls](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/plan_execute_review.rs#L187-L205).
4. [Перед review Core находит ID draft в model context, поэтому не переносит anchor на review answer](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/steering/weave.rs#L13-L35).
5. [Workflow сохраняет только финальный review answer и вызывает checkpoint](https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/workflow/coding-workflow/src/plan_execute_review.rs#L251-L256). [Core не находит draft-anchor в результате и возвращает ошибку](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/core/runtime/steering/weave.rs#L74-L104).

В обоих падающих сценариях ID в тексте ошибки в точности принадлежит **третьему**, execute-draft ответу. Это дополнительно проверяет `verify.py`, а не только выводится из исходников.

## Направление исправления

Согласовать lifetime/identity приватного execute draft с plan: приватная request-only проекция не должна оставаться durable response anchor. Возможный локальный путь — применять к draft тот же отдельный request-scoped ID, что уже используется для плана, и проверить перенос steering на persistent final response. Это предложение, не готовый проверенный патч.

Не следует просто отключать проверку исчезнувшего anchor или безусловно дописывать уточнение в хвост: это скроет реальные нарушения порядка и потери инструкций. Регрессия должна проверять оба момента доставки, отсутствие дубликатов и совпадение warm/cold history.

## Проверки и ограничения

- Ранее собранный module unit target: **7 plan_execute_review tests passed**; `baseline-modules.log`.
- Ранее собранный Core unit target: **1 существующий steering boundary test passed**; `baseline-core.log`.
- Изолированный end-to-end: **15 запусков**, 6 воспроизводимых failures и 9 успешных controls. Каждый запуск дополнительно cold-resumed.
- `verify.py`: все 15 наборов фактов согласованы, warm/cold projection равны.
- `regression.py`: желаемый инвариант по записанным прогонам: **3 passed, 2 expected failures**. Этот скрипт проверяет результаты `run.py`, сам runtime повторно не запускает.
- Полный workspace gate, реальный пользовательский harness, GUI и live provider не запускались. Поведение искусственной модели выбрано детерминированно для проверки ветвления; частота возникновения у реальных моделей не измерялась.

Повтор: `python3 run.py`, затем `python3 verify.py` и `python3 regression.py`. Пути к pinned executable/modules и test fixture Core в скриптах надо заменить на локальные. `run.py` создаёт только синтетические временные сессии; исходники не патчит.
