# Proteus: nested background lifecycle and event attribution

Core: `89997df995df7c39b713e16aba216ecb19c8f497`. Изолированная чистая копия исходников; production-код не изменялся. Пять model-free прогонов используют настоящие процессы `proteus server stdio`, штатный component workflow protocol и встроенные collaboration tools. Ни одного обращения к живой модели, внешнему сервису или пользовательским данным. Публикаций, коммитов и PR нет.

## BGC-1. Фоновый внук теряет канал событий и вопросов после завершения родителя (P2, depth ≥ 2)

Последовательность:
1. Root запускает child через `spawn_agent`.
2. Child запускает своего background child и возвращает успешный ответ, не вызывая `wait_agent`.
3. Внук спустя 1,5 секунды продолжает работу. Его процесс и runtime живы.
4. Прямой child уже возвращён в process pool; root больше не исполняет `drive_turn` для его stdout. Отдельный stdout reader лишь складывает события в ограниченную очередь.

Наблюдения в реальном процессе:
- `background`: внук вызывает `list_agents` и успешно завершает workflow. Локальные маркеры подтверждают это. Root получил его `SubagentStarted`, но не получил последующие tool events и `SubagentFinished`.
- `ask-background`: внук начинает штатный `request_user_input`, но root не получает ни одного `UserInputRequested`; workflow остаётся ждать ответа. Вопрос не является запрещённым tool: он включён в конфиге и разрешён fixture policy.
- `ask-background-resume`: спустя три секунды root делает `followup_task` тому же child. Child возобновляется в том же durable session, generation 2, но вопрос так и не появляется. Его `wait_agent(timeout_ms=100)` видит ещё работающего внука и возвращает `timed_out=true`.
- Положительный контроль `ask-wait`: если child сам остаётся в `wait_agent`, тот же вопрос проходит до root, валидный пустой ответ возвращается обратно, и workflow внука завершается. Наблюдались ровно один вопрос и один ответ.

Причина:
- `crates/proteus-core/src/core/agent_control/process/mod.rs:309–318,495–512`: routing принадлежит только активному turn; после него процесс становится idle.
- `process/mod.rs:293–299`: даже при resume первым действием вызывается `drain_stale_outputs`.
- `process/child.rs:138–140` + `process/output.rs:97–105`: drain удаляет накопленные frame-ы, наблюдая только session identity; он не форвардит pending user input, lifecycle или tool events.
- `process/turn.rs:418–434`: интерактивные запросы обслуживает только активный обработчик; pending snapshots этот путь не восстанавливают.

Условие: process backend, разрешённая вложенность (в проверке `max_depth=3`), collaboration child запускает фонового потомка и завершает свой turn раньше него; процесс сохраняется в idle pool. Проблема не требует совпадения call ID, перегрузки, ошибки worker-а или CLI бездействия. Root stdio клиент во всех проверках непрерывно читает stdout.

Влияние: пользователь не видит вопрос работающего потомка и не может ответить через root; status/progress остаётся неполным. В зависимости от конфигурации потомок ждёт timeout/отмену. Факт timeout/переполнения очереди в этой серии не воспроизводился, и потеря durable результата не заявляется: самостоятельная история потомка существует, а его parent control plane остаётся живым.

Направление исправления: постоянный process/session-owned dispatcher для lifecycle и interactive control, независимый от активного root Send; нельзя считать все idle outputs устаревшими. Альтернатива — явно запретить finish parent при незавершённых потомках или ограничить такую вложенность, если её поддержка не предполагается. Простое увеличение buffer/timeout причину не устранит.

## BGC-2. Вложенные события теряют исходного владельца даже при активном родителе (подтверждённый attribution defect)

В контрольном `wait` root → child → grandchild все уровни дожидаются завершения. У внука уникальный call ID для `list_agents`. Root получает его `ToolCallRequested`, `ToolCallResolved`, `ToolFinished`, но их `envelope.thread_id` равен ID прямого child, а не ID внука из `SubagentStarted`.

Последний authoritative root `SessionSnapshot` содержит `list_agents` внука в `parent.subagent.tools`. Это не только Desktop rendering и не ранее найденная коллизия одинаковых call IDs. Положительный user-input контроль также получает origin прямого child вместо внука.

Причина:
- `process/turn.rs:389–394`: извлекается только `envelope.event`; исходные session/thread/turn теряются.
- `process/turn.rs:116–137`: всем событиям выдаётся фиксированный context прямого child.
- `process/turn.rs:124–130`: origin интерактивного запроса также заменяется на прямого child.

Последствие: root display/control plane не различает работу прямого ребёнка и его потомка. Доставку ответа не тому процессу этот тест не доказывает: без коллизий запрос по сохранённому request ID в активной цепи успешно возвращается нужному внуку. Если flattened UI намерен, это всё равно следует обозначать как aggregate, а не точное происхождение. Приоритет зависит от обещанной семантики nested UI; не считать самостоятельным security finding.

Направление исправления: переводить собственный physical root ребёнка в его logical child ID, но сохранять/корректно отображать descendant attribution; для этого routing должен знать source root identity, а не безусловно заменять каждый envelope.

## Проверенное отрицательное наблюдение

Штатный `SubagentFinished` прямого ребёнка не опережает его durable history commit. `runtime/turn.rs:473` await-ит commit; `app_server/runs.rs:184–231` завершает projection/terminal state до oneshot результата; stdio публикует Response; process runner лишь после ответа эмитит `SubagentFinished`. Ранний workflow `TurnFinished` child-forwarder наружу не пропускает. Поэтому гипотеза о stale readonly child из-за такого порядка в штатном completion не подтверждается.

## Воспроизведение и ограничения

Файлы:
- `nested_fixture.py`: model-free workflow с тремя реальными peer-процессами.
- `run_nested.py`: активный контроль и background completion.
- `run_nested_input.py`: активный/background user input.
- `run_nested_resume.py`: background user input плюс follow-up.
- `verify.py`: assertions **наблюдаемого ошибочного поведения**, не fixed-code regression suite.
- `*-outputs.json`, `*-markers.jsonl`, `*-stderr.log`: фактический stdout root и маркеры fixture.
- `verification.log`, `build.log`, `revision.txt`: выполненные проверки и provenance.

Скрипты содержат локальные пути к изолированной рабочей копии, собранному бинарнику и подготовленному reference-module fixture. Для другой машины их нужно заменить. Полная пересборка `cargo build --locked --offline -p proteus-core --bin proteus` прошла; после неё выполнены все пять сценариев.

Область покрытия: настоящий process pool, stdio, collaboration tools, user input bridge и root snapshot. Не запускался настоящий provider, Desktop UI, HTTP/SSE, PTY и полный test suite. `ToolTerminalBound` отсутствует в child forward filter, но отдельный дефект по этому наблюдению не заявляется: UI semantics не проверялась.

Первый подготовительный user-input прогон без `tools.enabled` получил `unknown tool`; он сохранён в `setup-attempt/` только как setup diagnostic и не считается результатом продукта. Итоговые user-input проверки выполнялись после исправления test configuration.
