# Убрать повторную работу, сохранить проверки границ

Одна проверенная волна от 2026-11-17 вместо отдельных мелких PR.
Общий принцип: уже полученный результат использовать один раз; не удалять
проверку нового входа, другой ошибки или самостоятельного consumer.
Новые frameworks, caches и массовое удаление тестов не нужны.
Подробные отчёты ниже фиксируют локальные этапы до публикации;
фактический scope этого общего изменения указан отдельно здесь.

## Что меняется реально

**В этом dot repository применяется только test-fixture cleanup:**
`build-speed/desktop/diff-crate/test_qualify_diff.py` валидирует shared fixture,
которую эти тесты не меняют, один раз после загрузки, вместо 14 повторов в `setUp`.
Все 14 test methods/assertions и 27 parser-boundary validations сохранены.
Invalid fixture по-прежнему не может дать ложный успех negative test;
диагностика переходит из setup error в import/discovery error.
Production parser, workflows, исторические receipts/freezes не меняются.

**Core и Modules здесь только proposals, не upstream integration.**
Их patches лежат в отдельных каталогах и применяются к исходным репозиториям,
не к корню dot. Pins и установленное приложение не меняются.

| Участок | Удалённая работа | Сохранённая защита |
| --- | --- | --- |
| [Query classifier](query/README.md) | Поглощённый словарь из 23 entries и четыре невозможных suffix conditions | Tokenizer, stopwords, numeric/short early reject, dedup/order, 4-query cap, Unicode fallback |
| [Workflow output](workflow-output/REPORT.md) | Два временных owned strings и повторный полный подсчёт Unicode scalars | Trim, output/error order, точная граница 2,000 scalars и truncation suffix |
| [Core model alias](core-alias/REPORT.md) | Предварительный lookup перед тем же проверяющим lookup | Тот же unknown-alias error до мутаций, scope selection и child-local semantics |
| [Dot test fixture](test-fixture/REPORT.md) | 14 одинаковых fixture validations заменены одной | Все методы, assertions и per-invocation parser validation |

Numeric-only guard query оставлен: он может полезно отсеивать вход до следующих
scans. Аналогичные названия тестов не означают одинаковый инвариант, поэтому
diff/tabs suites и другие lanes не удалены. Замеров ускорения/RSS нет.

## Что действительно запускалось

| Scope | Baseline → candidate | Независимая проверка | Композиция |
| --- | --- | --- | --- |
| Query, Rust | Те же 3 methods PASS, с расширенными cases до production edit | 3 PASS | 3 PASS вместе с workflow patch |
| Workflow output, Rust | Те же 5 methods PASS, включая новую boundary matrix на baseline | 5 PASS | 5 PASS вместе с query patch |
| Core model/inline, Rust | Те же 12 existing methods PASS | Source review и проверка logs | 15 PASS на combined #167/#171 + alias |
| Dot pure Python | 14 diff + 12 tabs methods PASS до/после | 14 diff PASS и invalid-fixture oracle | Не требует Core/Modules composition |

Повторные исполнения не считаются новыми уникальными тестами. В query расширены
три существующих метода, в workflow добавлен один метод с шестью boundary cases;
Core и dot methods не добавлялись и не удалялись. Dot oracle отдельно проверяет
один negative test с valid/invalid fixture до/после, не выдаётся за новую suite.

Native Rust/Cargo 1.95.0 и Python 3.12.14. Exact commands, тестовые имена и
ограничения находятся в отдельных reports и verification manifests.
Changed-file fmt/diff, strict apply/reverse и independent review пройдены.

## Базы и порядок применения

- Modules proposals: `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7`.
  Фактический неизменённый Core pin: `185225a7103088c444788374ca425d230060f55a`.
- Core alias: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`.
- Dot test fixture: `99b88e2dd2be8d38a2d407756cfd903ed49de990`.

Два Modules patches меняют разные пути. Strict application в обоих порядках
даёт одинаковые bytes, reverse восстанавливает базу; на общей candidate tree
повторены только указанные 3+5 tests. [Точные hashes](MODULE-COMPOSITION.json).
Это не совместный Core/Modules gate с новым Core pin.

Core alias автономен и отдельно квалифицирован на combined #167/#171 (#175).
С #177 standalone и #181 проверена только парная source/apply композиция
в обоих порядках. Не применять raw #167/#171 повторно поверх combined пакета.
Ранее известные конфликты других persistence proposals не исправлены этой волной;
общий runtime-pass цепочки #167/#171/#177/#181 не заявляется.
В частности, #181 требует rebase к formatted #175 / `b2c285f`; эта комбинация
пока не qualified. Парный static apply с alias patch не заменяет этот rebase
и не является native-проверкой композиции #181 с #175.

## Границы

**NOT RUN:** full workspace/package gates, process/HTTP/provider/security
fixtures, qualification controllers, portable/GUI/install, hosted CI и benchmarks.
Компиляция lib test target не означает исполнение отфильтрованных fixtures.
HOLD, включая typed-memory, priority, revision, deadline, image и coordinated
optional-file-id rollout, не переоткрывались. Отказанные направления не повторялись.

Пакет хранит три квалифицированных upstream proposals и evidence одной реальной
dot test cleanup. Его merge не означает исправление production Core/Modules.
