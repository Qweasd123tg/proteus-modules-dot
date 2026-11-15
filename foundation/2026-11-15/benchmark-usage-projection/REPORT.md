> Publication note: this is the historical source-only stage. The later RUNTIME-SUPPLEMENT.md records six targeted synthetic tests passing on the same patch. Other gates remain unrun. References to raw evidence describe reviewed retained artifacts, not files included in this public package.

# Short/long benchmark usage: один владелец projection

## Итог и точный scope

Подготовлен **source-only candidate для известного F3** из PR85 testing-fidelity. Короткий report сейчас воспринимает numeric provider_usage как полный расход, не сохраняя lifecycle-completeness, тогда как long_report уже разделяет complete totals и observed lower bounds. Candidate переносит эту существующую long-report policy в небольшой общий модуль и использует её в обоих отчётах.

Это не новая finding и не утверждение, что опубликованные успешные benchmark tables неверны. Сохранённые result/grade/metrics/reports не пересчитывались, не исправлялись и не менялись. Pipeline/grader, сравниваемые arms, фильтры, hashes и правила первичных/повторных попыток не меняются.

**F1/F2 terminal/recovery classification и F4 missing native usage rows остаются открытыми.** Политика usage_completion перенесена, а не исправлена или объявлена универсально достоверной. Никакой claim «benchmark accounting полностью исправлен» не делается.

Независимый source review не нашёл blocker. Ни Python-код проекта, ни tests, ни imports, ни compilation, ни harness/runtime не выполнялись. Шесть тестов только предложены, NOT RUN.

## Версии и дедуп

- Core main bcbda4435534a296c707a1daa250813d692f68e1.
- Modules main c035142558f0fca43e9772fc0e50ca293abf1531.
- Delivery main при начале a038b7856a3b9bb8c862ee8553c553208c81b76a, включая PR125 hook-deadline HOLD.
- Core benchmark Python source анализируется отдельно от Modules' Core dependency pin 41bdfffa6e70228278b4abc758b7f81a12672f35.

Known F3/F4 evidence из прежнего Core89997df9/Modules3270dc0 сохранён в PRIOR-F3-F4.md, но его прежние запуски не повторялись. PR119/124 file-read proposals и их rebase относятся к другой границе; PR125 остаётся HOLD.

SOURCES.json/READ-VERIFICATION.json: 12 exact Git blobs. Сохранённые полные файлы нужны для source identity, а не для заявления полного audit каждого участка. Review ограничен usage/projection и релевантными consumers/docs/tests. Auth/sandbox/security/flagged направления не исследовались.

## Изменение

Новый usage_report.py содержит выбранную accounting policy, а не framework:
- TOKENS и четыре функции read_json/json_lines/known_sum/usage_completion перенесены из long_report.
- project_usage владеет row projection: reported_usage сохраняется отдельно; observed_partial_usage удерживает доступные суммы; tokens становится unknown по существующей completeness policy.
- summarize_usage владеет прежними long-report формулами totals, known_token_runs и observed_token_sums.
- short report сохраняет timed_out/returncode, вызывает общий projection и использует общую агрегацию. Старые flat input/cached/output fields остаются, но partial run больше не превращается в полный total только из-за числа.
- long report вызывает те же функции вместо собственного блока. Его status classifier, field formulas и selection остаются прежними для schema-valid artifacts.
- README объясняет complete/observed/unknown и coverage.

Четыре перемещённых function bodies текстово идентичны прежним, что проверено без их загрузки или выполнения. Исходные raw reported numbers не арифметически «исправляются». Единственный новый владелец policy позволяет менять её позднее согласованно, вместо независимых short/long правил.

## Что сохраняется и что намеренно меняется

Сохраняются:
- Pass = pipeline_ok AND grade; отдельные результаты graders/pipeline не переоцениваются.
- Duplicate-run и prompt/repository identity guards.
- Primary attempt==1; repeats по-прежнему учитываются отдельно.
- Множества runs выбирает caller: short primary и long observed-primary остаются своими прежними наборами. Pending/ungraded cases и grouping не унифицируются произвольно.
- Existing complete, valid integer totals ожидаются прежними по исходникам. Это не проверенное сравнение всех исторических таблиц.
- Long projection сохраняет значения для ожидаемой схемы данных, не обещает byte-identical JSON ordering или Python object alias identity.

Меняется short representation:
- При неполном lifecycle полный input/cached/output становится null, reported subtotal остаётся доступен отдельно.
- JSON получает reported_usage, observed_partial_usage, completeness reason и per-category coverage/sums.
- Token total использует long-report strict integer policy, а не старое «любое non-None значение». Requests/actions остаются на прежнем complete_sum.
- CLI продолжает печатать flat fields; нижние границы доступны в JSON, а не тайно подставляются вместо полных чисел.

Пример плана fixture: complete primary input=10 и incomplete primary reported input=20 дают complete input=null, observed sum=30 и known_token_runs=1. Repeat input=1000 не входит в эти primary totals. Это описание assertions предлагаемого теста, не исполненный результат.

## Важные пределы

- usage_complete — существующая lifecycle policy, не сертификат наличия всех token categories. Даже complete run может иметь tokens[field]=null.
- F4 может испортить completeness раньше report boundary: adapter отбрасывает отсутствующую целую usage row. Candidate этого не обнаруживает и не исправляет.
- F1/F2 выбранная классификация recovery/length не меняется; её недостатки не становятся устранёнными от вынесения функции.
- known_token_runs сохраняет прежний long-report критерий value is not None. Это не strict-int coverage validator для malformed artifacts. known_sum требует именно int, а observed fallback использует прежнее or 0. Произвольные bool/string/float inputs не объявляются корректными или эквивалентно обработанными.
- Observed sum=0 при coverage=0 не доказывает нулевой полный расход. Unknown нельзя использовать как ноль при сравнении стоимости.
- Функции суммируют только выбранные caller-ом наблюдаемые runs, не гарантируют полноту всех запланированных benchmark cells.
- Для неуспешных native runs short report теперь может читать stdout/native usage artifacts, как прежний long report. Это новая read/error dependency и дополнительная работа. Успешный pipeline без timeout проходит прежнюю быструю classifier branch без такого чтения.
- Existing JSON/read errors classifier не маскируются новым fallback. Нельзя обещать, что любой старый metadata-only short report по неполному artifact directory теперь соберётся.
- Нет runtime speedup или memory benchmark claims. Helper создаёт небольшие usage dictionaries; это не оптимизация числа allocations.

## Измеримая структурная польза

Два report paths теперь используют одну lifecycle/projection/aggregation policy вместо несовместимых «numeric presence» и «complete/partial» правил. long_report.py сокращён с 694 до 629 строк; общий связный helper — 82 строки. report.py: 83→91. Совокупно production Python этих файлов: 777→802, то есть +25 строк на исправленную boundary, а не заявленное сокращение всего кода.

Основная польза — единое место решения completeness и сохранение evidence, не отрицательный LOC. Не добавлены классы состояний, зависимости, универсальный loader, новая benchmark schema machine или изменение runner.

## Шесть предложенных tests, NOT RUN

1. Short/long row projection на complete и timeout synthetic artifacts, reported subtotal не теряется; входные files не меняются.
2. Mixed primary coverage, grader failure отдельно от usage completeness, repeat exclusion и одинаковые token aggregates при одинаковом выбранном наборе.
3. Complete lifecycle с отсутствующей category и доступным partial subtotal.
4. Явный ноль отличается от отсутствия наблюдения по strict totals/coverage; reported и masked fields независимы.
5. Existing Pi/Proteus teardown-completion policy не заменяется одним pipeline boolean.
6. Сохраняется prompt/repository identity guard.

Не запускался даже syntax/import check. Предлагаемый future focused gate при разрешённом выполнении: python3 -B examples/performance/coding-harness/usage_report_test.py. Он использует synthetic artifacts без model calls. Это инструкция для будущей проверки, не выполненная команда.

## Выполненные проверки и артефакты

- 12 exact source blobs проверены Git SHA и SHA256.
- EXTRACTION-VERIFICATION.json: текстовое равенство четырёх перемещённых функций.
- git apply --check --whitespace=error и inert apply; applied bytes совпадают с after/.
- Independent exact source review: USAGE-INDEPENDENT-REVIEW.md.
- MEASUREMENTS.json содержит только source counts.
- shared-usage-projection.patch SHA256: c1c30727c0a76fecea815caf22bcb8ed14fdc2e6bd98ab8877027551c760866f.

Никакие сохранённые benchmark результаты не редактировались и не перепубликовывались. Production/upstream refs не изменены. Готов только непроверенный source candidate для F3.
