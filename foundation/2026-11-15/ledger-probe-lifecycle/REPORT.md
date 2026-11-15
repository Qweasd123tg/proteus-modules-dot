# Ledger F2: instrumentation до импорта решения

Source candidate с ограниченными stdlib synthetic controls для известного benchmark-design F2/P2 из PR85. Это не новая finding и не пересмотр результатов benchmark. База Core `bcbda4435534a296c707a1daa250813d692f68e1`; Modules `c035142558f0fca43e9772fc0e50ca293abf1531`; delivery `6c5db812c792a6c115b3ff986c91fc3659bb3662`. Изменяются только private grader и его локальная документация в отдельной копии. Upstream, delivery и исторические scores не изменены.

## Общий invariant и решение

Инструментированная функция должна быть установлена **до первого импорта проверяемого решения**, а наблюдения должны относиться только к проверяемой операции. Release contract прямо требует `os.fsync` и `os.replace`, но не запрещает direct imports или сохранение функции в default argument. Текущий grader импортирует ledger раньше, чем ставит spies, поэтому эти обычные формы обходят его наблюдение.

Два существующих теста теперь вызывают один небольшой private probe script в свежем interpreter. Он устанавливает wrapper до импорта публичного `ledger.Store`, без знания `ledger.storage`, `ledger.store` или другого внутреннего layout. Используется тот же Python executable и solution cwd `/app`; штатный `long_corpus.prepare` уже копирует весь grader directory.

- Replace wrapper сначала вызывает настоящую функцию. Ошибка включается только после прежнего setup: put, успешный compact, второй put, foreign file и snapshot bytes. Проверяются достижение fault, распространение OSError, byte equality всех прежних файлов с прежним исключением `.lock`, отсутствие новых temporary files и чтение последнего значения после reopen.
- Fsync wrapper действительно вызывает прежний `os.fsync` и классифицирует настоящий descriptor. Наблюдения очищаются после import/open и между append/compact. Сохраняются пороги: file sync при append, минимум два file sync и directory sync при compact.
- Родительский pytest требует zero child returncode и показывает stdout/stderr при ошибке. Child использует explicit if/raise, а не removable Python assert: inherited optimization не отключает эти пять проверок. Это исправление внесено после независимого review.

Не добавляется новый local timeout или новая OS isolation. In-process purge/reload ledger не используется: он добавлял бы необходимость восстанавливать module identities и reasoning об уже захваченных внешних ссылках/import effects. Fresh process здесь служит чистой import lifecycle, не security boundary.

## Что сохранено и что стоит дороже

- Имена двух pytest tests сохраняются. Все остальные 20 top-level functions, включая остальные test bodies/helpers и decorators, AST-неизменны. 18 именованных test functions до и после; это не утверждение о выполненной pytest collection или числе parametrized passes.
- Public solution API, prompt, release docs/tests/fixtures и reference implementation не меняются. Патч не подменяет решение и не ослабляет disk/fsync thresholds.
- 269 строк прежнего grader заменяются 254 строками test_outputs.py плюс 78 строками probe, всего **+63 Python строки**, и 21 строкой документации. Выгода — устранение зависимости оракула от import style, не сокращение LOC.
- Два дополнительных interpreter starts создают overhead. CPU/RSS/latency и полный grader budget не измерены; ускорение не заявляется.

## Source-проверка

11 исходных Git blobs сверены по exact identity. Final patch SHA-256:
`10434bcde9866f02068b62019bf113bec9d509f17be059e4155f8281f6949869`.

`git apply --check`, применение в отдельную копию, byte-for-byte сравнение с after и AST parse Python source выполнены. AST parse не выполняет grader/solution. ASSERTION-PRESERVATION.json и SOURCE-CHECKS.json фиксируют границы. Независимые CONTRACT-REVIEW.md и SOURCE-REVIEW.md подтверждают final candidate; initial removable-assert caveat закрыт текущей ревизией.

## Фактически выполненные synthetic red/green controls

После source review отдельно выполнен RUN-TARGETS.py с зафиксированными input hashes, на **Python 3.12.14**. Его SHA-256: `0cd086dbf1026fa154a42caf965cf5d19a2281b4cd623a6aeaa4c7d20dfa23d6`.

| Срез | Фактический исход |
|---|---|
| Baseline, qualified imports | 2 probe invocations success |
| Baseline, direct imports | 2 ожидаемых assertion failures: DID NOT RAISE OSError; отсутствие file в fsync observations |
| Candidate, qualified/direct/default-captured imports × два probes | 6 success |
| Candidate, восемь намеренно неверных synthetic implementations | 8 ожидаемых отбраковок по нужной диагностике |
| Candidate, explicit -O: два positive и два negative controls | 2 success и 2 ожидаемых отбраковки |

**22 controls совпали с ожидаемым исходом. Это не 22 прошедших pytest tests:** в числе controls 12 ожидаемых отказов, включая два baseline reds. Candidate-only: 18 invocations, из них 8 success и 10 expected rejects.

Отрицательные fixtures проверяют отсутствие append fsync, только один compact file sync, отсутствие directory sync, проглоченную replace error, утечку temporary file, изменение journal после failure, неправильное значение при reopen и OSError до достижения injected replace fault. -O отдельно сохраняет отбраковку no-append-sync и leaked-temporary fixtures. В baseline выполняются два настоящих test bodies с минимальным stub только для pytest decorators/raises; остальные тела не вызываются. Candidate выполняет настоящий io_probe.py как __main__ через runpy, а не копию его алгоритма.

Во всех случаях используется написанный для контроля **синтетический JSON Store**, а не reference, submitted solution или корректная реализация Ledger2. Он выполняет настоящие локальные os.fsync/os.replace на private временных файлах, но не реализует codec/recovery/concurrency контракт Ledger2. Actual imported fixture path проверяется даже при ожидаемых исключениях. Исходные source/before/after, patch/runner и execution copies byte-неизменны до/после. `runtime/RESULT.json` SHA-256: `cc16c13595f56596ab3919e51472792dc46ebe865f9fd719406518d088a941f5`; stdout/stderr каждого случая сохранены.

Children запускаются с -I/-B. Python audit hook до project/fixture code отвергает socket events; selfcheck проверяет отказ при создании socket, соединение не выполняется. В проверяемом коде нет внешних API/LLM-вызовов или неизвестных исполняемых решений. Это **не OS network namespace, не network capture и не общий sandbox claim**. Optimization controls используют явный -O, а не интеграционный запуск с inherited PYTHONOPTIMIZE. Timeout15 относится только к этому synthetic harness, не к candidate grader contract.

HARNESS-SOURCE-REVIEW.md содержит review до выполнения, RUNTIME-REVIEW.md — независимую проверку полученных результатов. SOURCE-CHECKS.json отделяет source checks от runtime/RESULT.json.

## Что ещё не выполнено

- Новый parent run_io_probe wrapper внутри настоящего pytest, штатная case preparation и packaging execution.
- Полный grader/public suite на настоящем Ledger/reference, baseline/candidate real gold refactors или исторические submitted workspaces.
- Python3.13.9/pytest8.4.1 штатного benchmark, Core/Modules/native workflow runtime, live providers и новый benchmark.

Эти проверки остаются integration/qualification gate. Source-level copytree подтверждает доставку соседнего helper по коду, не заменяет фактическую подготовку case. Историческое F2 evidence относится к прежнему Core89997df9 и не превращается в нынешний full-grader PASS.

Scope — публичные Python os-функции, установленные до первого ledger import. Не заявляется универсальный syscall interception, полное доказательство crash safety или покрытие альтернативных implementation boundaries. Отдельный C/syscall framework не нужен для доказанного дефекта. PR130 устраняет иной loader дефект journal grader; PR126–128 относятся к accounting. #131/#132 и prepared-request accounting HOLD здесь не затрагиваются.
