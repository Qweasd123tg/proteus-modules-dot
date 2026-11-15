> Publisher note: это статический план на delivery `97d853b`. Upstream refs ниже исторические; действующие базы семи source-кандидатов находятся в [общем отчёте](REPORT.md). Publisher повторил equality/AST/hash checks отдельно, без запуска project code. План ничего не удаляет и не меняет CI.

# Proteus: доказанная дедупликация без удаления защиты

## Вывод

Есть два конкретных кандидата на общий владелец кода в delivery-репозитории. Они не требуют нового framework: четыре копии существующего CI envelope и две копии skills probe/verifier. Дублирование доказано по содержимому, а не по похожим именам. Сначала объединяется реализация, затем её тесты. **Безусловно безопасных удалений выполняемых тестов на текущем дереве: 0.**

Это план изменения, не готовый production patch. Он снижает цену поддержки CI, но не ускоряет runtime Proteus. Ускорение CI также не измерено. Для runtime приоритетнее уже опубликованные небольшие owner/codec-рефакторы и их проверенная композиция, а не новый универсальный слой.

## Точная база и проверки

- Delivery: `Qweasd123tg/proteus-modules-dot`, main `97d853bba033b02f996625967e0087b00d606c76`, включает merged PR164.
- Historical source heads первоначального анализа, не базы этого пакета: Core `bcbda4435534a296c707a1daa250813d692f68e1`; Modules `c035142558f0fca43e9772fc0e50ca293abf1531`; Desktop `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
- Проверены 20 прочитанных source blobs: локально вычисленный Git blob SHA равен ответу file API и SHA из полного дерева выбранного delivery commit.
- Авторский `analyze.py` читает строки/JSON, использует `ast.parse` и `ast.literal_eval`, не импортирует и не запускает репозиторный код. Все статические проверки прошли.
- Прочитаны Core AGENTS/testing standard, существующие model-stream и workflow-json simplification reports, reviewed-simplification, README/VALIDATION и потребители CI. Публикация старых patch-кандидатов не объявляется внедрением в upstream.
- Не запускались репозиторные тесты, process controllers, Rust/Cargo, зависимости, GUI или CI. Не изменялись upstream, CI workflows или active sources. Не было попыток обходить запреты.

## 1. Envelope: один existing controller, отдельная политика каждого entrypoint

Четыре файла `envelope.py` по 386 строк совпадают **побайтно после удаления одной строки DEADLINES**:

| Каталог | Различие политики |
|---|---|
| `ci/resource-envelope-v1` | core-skills=1800, evidence-spans=1500 |
| `ci/strict-fullturn` | те же два + strict-fullturn=2700 |
| `consumers/usage-attribution/ci` | usage-attribution=1800 |
| `examples/correction-memory/ci` | cas-runtime=1800 |

Соответствующие четыре `test_envelope.py`: по 277 строк и 35 методов. Первые две копии полностью идентичны (blob `8a7f527d09de6bc113e905b91725902a74e5eb34`). Две другие отличаются только десятью строковыми аргументами profile (`core-skills` → `usage-attribution` / `cas-runtime`). После ровно этой нормализации полные строки совпадают.

Это 105 повторных **определений** методов, не 105 доказанно ненужных запусков. Сегодня каждая копия тестирует свой sibling controller. Удалить три suites, оставив три независимые реализации, значит потерять защиту от их последующего расхождения.

### Минимальная форма изменения

1. Переиспользовать существующий controller как единственный owner filesystem/process-monitoring механики. Не писать новый supervisor, registry, plugin protocol, класс hierarchy или универсальный test runner.
2. Сохранить локальные profiles/deadlines в тонких entrypoints. Передавать mapping/selected deadline явно; не делать общий разрешающий union всех profiles и не прятать изменение политики в mutable global.
3. Один канонический набор существующих 35 методов. Не выкидывать assertion и не заменять его smoke-тестом только ради меньшего числа строк.
4. Небольшие wiring-проверки каждого entrypoint: допустимые/недопустимые profiles, фактический deadline в supervise и receipt, путь к shared code. Можно расширить существующий success/receipt case параметрами, а не создавать ещё одну большую suite.
5. Обновить consumers атомарно: CLI вызовы, isolated `python -I` import resolution, `--input` hashing полного executable closure, workflow path filters и exact-test-name gates. Проверить запуск из существующих cwd и отсутствие sibling fallback-копии.

Особенно важно: текущая strict-fullturn копия тестов вызывает `execute('core-skills', ...)`, а не strict-fullturn. Её 35 успешных методов сами по себе не доказывают выбор 2700 секунд для strict lane. При объединении нельзя выдавать тесты общей механики за проверку специфической policy.

### Карта сохраняемых инвариантов (все 35 существующих методов)

| Инвариант | Методы, без префикса `test_` |
|---|---|
| Артефакты: скрытые/специальные имена, точные bytes и пределы | valid_hidden_vertical_bar_snapshot; file_cap_from_valid_baseline; aggregate_cap_from_valid_baseline; count_cap_from_valid_baseline; path_cap_from_valid_baseline; depth_cap; bounded_read_exact_and_plus_one |
| Разные symlink границы | symlink_rejected; root_symlink_rejected |
| Изменение источника во время snapshot | snapshot_metadata_race; snapshot_size_race |
| Отказ до spawn при нехватке места/неверных output leaves/FS | low_disk_never_spawns; old_output_never_spawns; nested_output_never_spawns; different_filesystem_refused_before_spawn |
| Ограничение числа входов | input_count_bounded |
| Честные receipt и partial evidence | spawn_error_has_receipt; success_has_fresh_marker_and_bounded_archive; changed_input_keeps_command_success_separate; partial_archive_enumerates_retained_only; snapshot_low_headroom_is_failed_not_success; primary_deadline_survives_source_mismatch; final_receipt_failure_gets_explicit_partial_fallback |
| Cleanup ordering и отсутствие ложной settlement-гарантии | term_kill_before_any_reap; reaped_group_not_signaled; signal_denial_still_attempts_reap; wait_timeout_does_not_claim_settlement |
| Мониторинг/deadline/pipe/disk/error | deadline; disk; pipe; artifact; success_is_not_tree_settlement; nonzero; unconfirmed_nonblocking_setup_never_reads_pipe; initial_monitor_error_closes_selector_and_attempts_cleanup |

Эти группы не взаимозаменяемы: file cap ≠ aggregate cap; root symlink ≠ child symlink; mock cleanup order ≠ реальное завершение потомков. Их объединение в table-driven форму допустимо, удаление веток нет.

### Цена и ожидаемый размер

Сейчас production+test корпус: 4 × (386+277) = 2652 raw lines. Три полные копии занимают 1989 строк до учёта будущих wrappers/wiring. Это **не net diff** и не обещание удалить 1989 строк. Shared dependency добавляет import/packaging обязанность и требует согласованного обновления evidence closure. Широкий orchestration framework ради экономии десятков быстрых Python cases не оправдан.

Сначала сохранить запуск канонической suite в нужных CI lanes. Убирать повторное выполнение можно лишь при одинаковых kernel bytes, runtime, configuration и coverage, с обязательной проверкой wiring каждого потребителя. Число методов не равно времени CI; Cargo и интеграционные lanes не сокращать без измерения.

## 2. Skills: одинаковая механика, разные compatibility lanes

Между `conformance/core-skills/ci` и `conformance/current-core-skills/ci` идентичны:

| Файл | Raw lines | Методы | Git blob |
|---|---:|---:|---|
| run_probe.py | 146 | 0 | adb9bbefa3d0e287a022bd00e5fb3e8bc9d7979a |
| verify_results.py | 49 | 0 | 92c82ccf55a57bfe7cf16c3b6ab15199a17b6bfb |
| test_capture_controls.py | 50 | 4 | 0ae61b49562bbfa0544fe396efadcebb756ad57c |
| test_verify_results.py | 88 | 11 | c054f2f4d1a0348d83cebc07faca55180103df16 |

333 gross duplicate lines и 15 повторных определений методов. `scenarios.json` отличается только Core pin: `3f36a003...` против `1fc3ef22...`. Оба содержат одинаковые 11 имен behavior checks, но проверяют разные зависимые сборки. Это **не основание удалить один compatibility lane**.

Минимальный вариант: общий существующий probe/verifier и его tests, параметризованный источник scenarios для каждого lane. Оставить отдельные Rust/integration checks обоих pins и отдельные artifacts. Общие функции уже принимают expected data; не нужен новый abstraction layer. Не заменять probe.capture на envelope.supervise только из-за похожих циклов: первый декодирует UTF-8 и имеет другой API/cleanup/receipt contract.

| Сохраняемая граница | Существующие методы |
|---|---|
| stdout+stderr, overflow+reap, timeout+reap, ошибочный UTF-8 | complete_stdout_stderr; capture_overflow_kills_and_reaps_controller; deadline_kills_and_reaps_controller; non_utf8_is_not_silently_accepted |
| Проверка отчёта без подмены результата | valid_complete_control; omitted_check; duplicate_check; nonpassing_check |
| Strict types/JSON | boolean_schema_version; float_schema_version; nonfinite_json; duplicate_json_key |
| Identity и completion | wrong_core_pin; missing_completion_marker; changed_source |

Capture suite реально создаёт маленькие Python child-процессы. Её исходники прочитаны, но она здесь не запускалась. Envelope mock suite и эти process checks не дублируют друг друга.

## 3. Почему сейчас план, а не механическая правка

`ci/strict-fullturn/verify_ci.py::sources` сверяет payload bytes по `PUBLICATION.json`; `tests` требует exact named tests/counts. Workflows хешируют входные scripts и отбирают paths. Если вынести shared module и забыть добавить его в closure, можно получить stale/недостоверную аттестацию или вообще пропустить нужный workflow. Если просто удалить файл, frozen source gate закономерно перестанет проходить.

Исторические `PUBLICATION.json`, логи, baseline/solution snapshots и evidence hashes не надо тихо переписывать как будто прошлый запуск относился к новому коду. Новая active validation revision должна явно отделяться от старой аттестации. Имеющиеся snapshots и архивные tests остаются read-only evidence, а не целью очистки.

Этот evidence/packaging переход больше, чем удаление совпадающих файлов. Он требует отдельного scoped patch и review; сам набор source equality checks не доказывает корректность CLI/import/hash closure после такого перехода.

## 4. Правила для источников Proteus и уже опубликованных изменений

Core `docs/development/testing.md` на исследованном тогда head уже задаёт нужную модель: один инвариант на нескольких слоях оправдан только разными источниками ошибки; существующий сценарий предпочтительнее нового; focused/package/workspace не запускаются подряд, когда последний включает первые. Это следует применять, а не создавать конкурирующий test policy framework.

- PR106/107/108-class sampling/JSON/SSE simplifications не повторять как новые находки. Они уже убирают дублирование без общего workflow/adapter framework; опубликованные source candidates не равны runtime validation.
- Reviewed config/history simplification содержит новые regression cases для разных seams (Save/Load, workflow request history, compactor). Повторные process/regression запуски не считать новыми тестами; удаление по общему слову history не обосновано.
- PR164 отдельно предупреждает: 12 новых targeted methods + 6 адаптированных serialization methods на composed tree = 18, не 30 уникальных новых. Ни 12 compatibility checks, ни 6 serialization checks не лишние только из-за повторного запуска на standalone/combined базе.
- Архивные benchmark baseline/solution и vendored regression source copies имеют намеренно разные роли; одинаковый Git blob там не делает их redundant executable tests.

## Acceptance gate для будущей консолидации

1. Зафиксировать новый base и проверенный dependency closure; не распространять вывод этой ревизии на новое main автоматически.
2. Сравнить прежние/новые CLI policy, cwd, exit code, receipt fields, deadline arguments и failures.
3. На новой shared реализации выполнить все 35 envelope methods, 4 capture methods и 11 verifier methods без skipped/zero-selection, затем lane-specific wiring/fixture checks. Это не 170 уникальных behaviors: 50 канонических методов плюс новые реально необходимые wiring cases.
4. Прогнать каждый затронутый workflow source/test-name validator и negative stale/shared-source mutation case; сохранить full hash closure и workflow path triggers.
5. Не выдавать mocked filesystem/process controls за real descendant teardown, production Rust gate или performance benchmark.
6. Итоговый diff должен учитывать общие модули, wrappers, tests, manifests, docs и generated evidence. Если выигрыш съедает новый framework, остановить обобщение.

Приоритет: владельцы данных и существующие helpers в production; затем единый owner CI-кода. Массовое удаление тестов, новая система запусков или объединение независимых slot semantics не обоснованы.
