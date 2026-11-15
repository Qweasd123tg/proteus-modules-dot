# Selected binary: metadata и argv используют одну нормализованную identity

## Результат и точная граница

Подготовлен минимальный candidate для **известного пункта 1 benchmark-execution из PR85**, не новая finding. В Proteus-ветке `adapters.prepare` basename команды теперь выводится из того же `args.binary`, который runner нормализует и записывает в metadata. Вместо второй независимой константы `proteus` используется `args.binary.name`.

Фактически выполнены только четыре новых **synthetic command-construction tests** на каждой из двух изолированных копий:

- Baseline: default-name control проходит; три renamed-name assertions падают, без errors/skips.
- Candidate: **4/4 проходят**, без errors/skips.
- Python **3.12.14**, `-I -B -S`; exact imported-module paths и SHA256 проверены до/после.

Это не запуск оцениваемого executable, не интеграционный запуск runner, не реальный benchmark и не проверка фактической исполняемой версии. Исторические scores, timings и доказательства других пунктов отчёта не пересчитывались. Никакие security/process-policy изменения не входят в candidate.

## Исходники и дедупликация

- Core baseline: `bcbda4435534a296c707a1daa250813d692f68e1`.
- Delivery main при проверке: `2c5555590382527665bd7616a7358ad28f7006d1`, после PR140 HOLD.
- Восемь точных source/doc blobs сохранены в `sources/`; Git blob hashes и SHA256 подтверждены в `SOURCES.json` и `READ-VERIFICATION.json`.
- Известный источник: [PR85 benchmark-execution, пункт 1](https://github.com/Qweasd123tg/proteus-modules-dot/blob/2c5555590382527665bd7616a7358ad28f7006d1/research/proteus-continuous-audit-2026-11-13/evidence/benchmark-execution/REPORT.md), blob `84be9c9cdb046e97ca21ba1431d4f114ea239d52`. Старый process reproduction не повторялся и не используется как результат этого прогона.
- PR126–128 относятся к usage/terminal accounting; PR129 к phase accounting; PR130 к grader loading; PR133 к ledger probe lifecycle. Этот candidate не заменяет их и не затрагивает их контракты.

## Source-level причинная цепочка

1. [runner.py:202](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/runner.py#L202) делает `Path(...).expanduser().resolve()` и сохраняет результат в `args.binary`.
2. [runner.py:235](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/runner.py#L235) пишет именно этот путь и его digest в metadata.
3. [adapters.py:144](https://github.com/Proteus-harness/Proteus-core/blob/bcbda4435534a296c707a1daa250813d692f68e1/examples/performance/coding-harness/adapters.py#L144) независимо подставляет константу `/runtime/bin/proteus` в первый argv token.
4. Для normalized basename `proteus-candidate` metadata producer и command producer поэтому выбирают разные basename. Наличие соседнего `proteus` не должно быть альтернативным источником identity.

Общий инвариант здесь узкий: **производные metadata и argv не должны независимо выбирать имя выбранного binary**. Изменение одной строки удаляет эту вторую константу; новый объект/config/framework не нужен. Это correctness improvement, не заявление о производительности или значимом уменьшении LOC.

## Patch и совместимость

`binary-identity.patch`, SHA256 `cb71c8bf82286f0718f9d78118158e3100efb9cb237eedd84e1e97f468cbe4ca`:

```diff
- return ['/runtime/bin/proteus', '--config', '/runtime/configs/eval.json',
+ return ['/runtime/bin/' + args.binary.name, '--config', '/runtime/configs/eval.json',
```

Также добавлены четыре строки README с точной семантикой и отдельный 71-строчный test module. Всего 76 добавленных / 1 удалённая строка; production изменение 1-for-1. Другие argv tokens, нормализация пути и metadata format не меняются. Default basename `proteus` сохраняет прежний первый token. Space/Unicode basename остаётся одним элементом argv, без shell parsing.

Identity основана на **resolved target basename**, а не на исходном написании CLI аргумента: `resolve()` уже выполнен runner. Candidate не меняет существующую symlink semantics, не обещает executable-byte immutability между подготовкой и запуском и не подтверждает фактически исполненный digest.

Strict `git apply --check --whitespace=error` и apply выполнены в отдельной копии; полученные три файла побайтово равны `after/` (`APPLY-CHECK.json`). Механически проверена композиция с exact PR126 → PR127 → PR128: candidate до и после этой фиксированной цепочки даёт одинаковые файлы (`COMPOSITION.json`). Это **не combined runtime gate** и не проверка всех перестановок зависимых patches.

## Выполненные тесты и воспроизведение

`binary_identity_test.py` вызывает actual `adapters.prepare` с временными локальными config/case и plain fixture bytes, которые не являются executable code. До вызова замоканы `CORE`, `load_module` и `copy_auth`: нет загрузки native helpers, чтения настоящего auth или внешнего вызова. Выбрана обычная synthetic non-Go/non-Pi config ветка. Остальные project tests и runner не импортировались.

Оба прогона выполнялись отдельными процессами по схеме:

```sh
HOME="$PACKAGE/runtime/$LABEL/home" TMPDIR="$PACKAGE/runtime/$LABEL/tmp" \
  python3 -I -B -S "$PACKAGE/run_target.py" \
  "$PACKAGE/runtime/$LABEL/examples/performance/coding-harness" \
  "$PACKAGE/runtime/$LABEL-expected.json"
```

Здесь `$PACKAGE` — корень этого evidence package, `$LABEL` — `baseline` или `candidate`. Baseline содержит точные исходники плюс тот же новый test file; candidate содержит exact patch. Драйвер хеширует оба импортируемых файла, проверяет оба `__file__`, загружает только класс `PreparedBinaryIdentity` и ровно четыре tests, затем повторно проверяет hashes. HOME/TMPDIR принадлежат тестовой копии. Никакая сетевая изоляция этим не заявляется; проверенный путь не содержит внешних вызовов.

| Случай | Baseline | Candidate |
|---|---|---|
| Default `proteus` | pass | pass |
| Renamed candidate, sibling `proteus` существует | expected assertion failure | pass |
| Renamed candidate, sibling отсутствует | expected assertion failure | pass |
| Space + Unicode basename | expected assertion failure | pass |

Каждый успешно подготовленный command дополнительно проверяет неизменные остальные tokens, выбранный path и fixture bytes. Sibling test различает **имена**, а не доказывает запуск одного из файлов. Exact stdout/stderr и exit codes сохранены в `runtime/baseline.log` / `.exit` и `runtime/candidate.log` / `.exit`; baseline exit 1, candidate exit 0. `run_target.py` SHA256 `1e64b5d54b30ef648bd9e93241232bc9fe3bbdfbb5d4fd6d74bbccd5acd3e685`.

## Ограничения

Не выполнялись native CLI, evaluated executable, runner/main, process reproduction, provider/API/LLM calls, Rust/toolchain, full pytest/unittest discovery, upstream tests или benchmark. Auth/mount behavior не является предметом tests. Не проверены real metadata file emission, executable launch или file-content stability across launch. Upstream repository и production не изменялись. Python tests подтверждают только фактическое построение команды на synthetic fixtures.

Independent pre-run review и driver addendum находятся в `PRE-RUN-REVIEW.md`; final independent source/evidence review без блокеров находится в `INDEPENDENT-REVIEW.md`. Candidate не следует представлять как полностью интеграционно проверенное исправление benchmark execution.
