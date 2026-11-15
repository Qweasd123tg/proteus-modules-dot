# F4: expected usage rows отдельно от surviving observations

## Результат и граница

Подготовлен небольшой кандидат для **известного F4 / P3 robustness** из PR85 testing-fidelity. Pi и Codex больше не считают surviving usage subtotal полным лишь потому, что целиком отсутствующая usage row была отфильтрована. Один helper объединяет expected cardinality, per-category full totals, partial observations и coverage.

Это **не новая finding**, не доказательство обычной потери usage у pinned Pi/Codex и не пересмотр опубликованных benchmark scores. Изменение касается явно неполных/некорректных artifacts с наблюдаемыми completion events. Полностью исчезнувшие события и невидимые billable calls этим не обнаруживаются.

После independent source review выполнены actual scoped controls:

- Baseline Core + exact PR126 + exact PR127: **2 ожидаемых behavioral failures**, оба возвращают synthetic input subtotal `110` вместо unknown при второй missing usage row.
- Candidate: **7/7 новых tests**, **9/9 PR127 tests**, **6/6 PR126 tests** прошли, всего 22 candidate tests.
- Python **3.12.14**, без внешних dependencies/install, Rust, native CLI, external API/LLM, graders или benchmark reruns.
- Independent contract/source/runtime-evidence reviews сохранены. Это focused synthetic gate, не full CI suite или real native run.

## Exact dependency и исходники

Зафиксированные refs при начале и завершении одинаковы:
- Core `bcbda4435534a296c707a1daa250813d692f68e1`.
- Modules `c035142558f0fca43e9772fc0e50ca293abf1531`.
- Delivery `5f13f7ef1e06cb61abc9bb4000bffc1b3e2395e2`, включая [PR127](https://github.com/Qweasd123tg/proteus-modules-dot/pull/127).

Применение требует точной последовательности:
1. Core baseline выше.
2. [PR126](https://github.com/Qweasd123tg/proteus-modules-dot/pull/126), patch SHA256 `c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f`.
3. PR127, patch SHA256 `b2b457e7dd2cfb17e1489ef97728080c09b306d9dedd0456f5c2b65b8114a2ee`.
4. Новый `native-usage-on-pr127.patch`, SHA256 `bc59d34fd938485e8a9831c87d3c6e30a4e36b01814c52f37e538d4a40cc91ef`.

Это не standalone patch к чистому Core и не изменение upstream production/Modules pin. `before` побайтово совпадает с проверенным PR127 `after`. Семь original Core Git blobs отдельно сверены в `SOURCES.json`; последующие candidate bytes определяются exact dependency stack. Полные файлы сохранены для source identity; review ограничен accounting/projection и import dependencies, не security/flagged направлениями.

Исторический F4 и его точные ограничения сохранены в `PRIOR-F4.md`. [Исходные native branches](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/adapters.py#L239-L277) удаляют non-dict usage до проверки полей. Из-за этого старый `sum_usage` уже не знает, что существовал ещё один contributor. [Canonical measurement helper](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/code-mode/measurements.py#L77-L94) учитывает ожидаемую cardinality отдельно, но не переносится целиком: его request/journal ownership другой, импортирование его parser здесь не требуется.

## Общий инвариант

Для Pi `expected_usage_rows` — число наблюдавшихся assistant `message_end`; для Codex — число `turn.completed`. Это не число всех requests, `agent_settled`, prompts, неизвестных попыток или полного billed usage. Codex `model_requests` остаётся `None`.

Новый `usage_evidence(rows, mapping, expected_rows)` возвращает:
- `provider_usage`: full total только при positive exact-int expected count, совпадении числа observed dict rows с ним и наличии exact-int contribution от каждой row для данной category.
- `partial_reported_usage_sums`: сумма известных contributions либо `None`, если ни одного нет.
- `usage_fields_reported_by_rows`: число qualifying contributions по category.
- `expected_usage_rows`: denominator, выбранный native adapter.

Отсутствие usage, `null` или non-dict не превращаются в zero. Пустой dict сохраняется raw, но не предоставляет ни одной category. Отсутствие observations даёт partial `None`/count 0; одна явная zero observation — partial 0/count 1. Полный zero требует coverage всех expected rows.

Для Pi canonical input — `input + cacheRead + cacheWrite`. Helper вычисляет этот composite **внутри каждой row**, только когда все три компонента — exact integers. Компоненты разных неполных rows не считаются полным composite observation. Их собственные partial categories и raw blocks остаются доступны; composite observation сознательно более консервативен и не обещает максимально тесную lower bound.

Это одна небольшая функция и совместимый wrapper, не новый framework, schema machine или lifecycle policy.

## Сохранение данных и контрактов

- `native_usage` остаётся прежним списком реально найденных dict-valued blocks. Missing placeholders не вставляются, raw значения не переписываются и порядок не меняется.
- Обычные valid complete integer totals сохраняют прежние значения. Для полного Pi input сумма per-row composites равна старой сумме полных column totals. Это source equivalence плюс synthetic controls, **не сравнение всех исторических datasets**.
- Для вновь вычисляемых неполных artifacts прежний ложный full total намеренно становится `None`; его известные contributions сохраняются в partial sums. Нельзя одновременно исправить F4 и обещать прежнее ошибочное full-total значение для этого случая.
- `reported_usage` в reports сохраняет полученный **adapter `provider_usage`**, который теперь может быть strict unknown. Это не raw `native_usage`. Доступные numbers из неполных rows остаются в raw blocks и в partial evidence, а PR126 выводит их через `observed_partial_usage`.
- Generation/pipeline success, grading, model/provider/reasoning extraction, tool/model counters и PR127 outcome reducer не меняются. Завершённый task может иметь `usage_complete=true` по lifecycle и одновременно `tokens[field]=None` из-за отсутствующей category/row.
- `sum_usage(rows, mapping)` остаётся совместимым по значениям для прежних list-of-dict/string-mapping callers, делегируя helper с `expected_rows=len(rows)`. OpenCode получает прежние full totals; новая expected-event cardinality для него **не заявляется**. Wrapper теперь создаёт лишние temporary evidence dictionaries, затем отбрасывает их; это не performance optimization.
- Historical result.json, metrics, grading и опубликованные tables автоматически не пересчитываются. Report не восстанавливает completeness старого неправильно записанного subtotal, если native metrics не вычислены заново из source artifacts.

Production изменение ограничено `adapters.py`: **314→326 строк (+12)**. Ещё изменены README и добавлен dedicated test file. Нет claims об ускорении, снижении allocations/RSS или меньшем полном расходе модели.

## Что остаётся неизвестным

F4 исправляется только на observed-completion-to-usage boundary этих двух adapters. Missing whole completion event, malformed JSON line, активный запрос без completion, auxiliary usage вне stream, duplicate completion и корректность native counters по-прежнему не гарантируются. Это не ledger всех оплат.

Exact-int правило исключает bool/float/string, но сохраняет прежнее принятие negative integers. Sums являются lower bounds лишь при нормальных nonnegative token counters. Candidate не превращает произвольный malformed artifact в валидный financial/accounting record и не добавляет новую нормализацию.

Вне поддержанной формы rows/mapping helper может отказать exception; общего arbitrary-input validator или generator API не обещано. Общие ограничения PR126/127, включая stored historical pipeline success, generation-versus-postprocessing, Pi version boundary и legacy string taxonomy, остаются.

## Исполнение и воспроизводимость

`RUN-TARGETS.py` проверяет exact patch hash и соответствие всей исходной staged base PR127 `after`. В baseline-copy добавлен только новый `native_usage_test.py`, **без patched implementation**. Candidate-copy получена через strict `git apply --check --whitespace=error` и `git apply`; итог совпал с reviewed `after`.

Четыре запущенных commands, каждый с доступным Python `-B -E -S`, clean explicit environment и private HOME/TMPDIR:

```sh
python3 -B -E -S examples/performance/coding-harness/native_usage_test.py \
  NativeUsageChecks.test_pi_missing_whole_usage_row_is_not_a_complete_total \
  NativeUsageChecks.test_codex_missing_whole_usage_row_is_not_a_complete_total -v
# baseline: exit 1; FAILED (failures=2), AssertionError: 110 is not None

python3 -B -E -S examples/performance/coding-harness/native_usage_test.py -v
# candidate: exit 0, Ran 7 tests, OK

python3 -B -E -S examples/performance/coding-harness/pi_terminal_test.py -v
# candidate: exit 0, Ran 9 tests, OK

python3 -B -E -S examples/performance/coding-harness/usage_report_test.py -v
# candidate: exit 0, Ran 6 tests, OK
```

Оба red assertions стоят до доступа к новым fields; это не missing-module/import failure. Новые controls покрывают whole missing/null/non-dict usage, complete totals/raw preservation, empty/zero observations, per-row composite и invalid components, wrapper value policy и обе report projections с partial evidence. Integration fixture явно задаёт successful lifecycle; он демонстрирует независимость accounting completeness, не исполняет живую модель или grader.

`runtime/INPUTS-BEFORE.json`/`INPUTS-AFTER.json` совпадают для sources, before/after и обеих copies. Private HOME/TMPDIR после каждого run пусты. Сохранённые benchmark данные не использовались как изменяемые fixtures и не переписывались. No-API/native-call statement относится к проверенным selected paths; packet traffic не измерялся. Использован текущий platform sandbox, отдельная OS/network namespace не заявлена.

Test durations из logs не являются benchmark. Не выполнялись Rust, full harness suite, native Pi/Codex/OpenCode или installed-version validation. Если code/test bytes изменятся, эти результаты нельзя приписать новой версии без соответствующей проверки.

## Evidence

- `CONTRACT-REVIEW.md`: независимый предварительный invariant review.
- `SOURCE-REVIEW.md`: exact final patch/test source review; его NOT RUN описывает предыдущую стадию.
- `PATCH-VERIFICATION.json`, `final-apply-check`: inert apply/byte equality.
- `runtime/PREPARATION.json`, `RUNS.json`, `RESULT.json`, четыре log пары и manifests: фактические результаты.
- `RUNTIME-REVIEW.md`: independent actual-evidence review, без повторного исполнения tests.

Ничего не опубликовано мной, upstream production refs не менялись. Пакет пригоден как reviewed F4 robustness candidate с точной dependency chain и scoped synthetic red/green, не как объявление полного исправления benchmark accounting.

## Publication note
This sanitized delivery excludes raw runtime logs, private paths, source snapshots and local execution driver. Evidence paths above refer to retained review inputs, not all bundled files. Publisher independently verified seven source hashes/Git blobs, exact dependency blob identities, strict three-patch application and final byte equality, and stored log hashes. Publisher did not rerun tests. No upstream integration is claimed.
