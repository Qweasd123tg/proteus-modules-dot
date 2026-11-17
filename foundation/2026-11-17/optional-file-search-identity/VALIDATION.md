# Focused native evidence

Дата: 2026-11-17. Официальный Rust/Cargo 1.95.0. Все исполнявшиеся тела тестов предварительно прочитаны: serde либо synthetic JSON parser/state, без HTTP, процессов, credentials и живых hosted tools. Core runner при выбранном `proteus-contracts` target не строит process fixtures.

| Стадия | Реальный результат |
|---|---|
| Core, final valid fixture + исходный String DTO | 2 PASS + 1 expected RED: missing field `file_id` |
| Core, Option candidate | 3/3 PASS, 0 filtered |
| Modules, candidate contract + старый обязательный parser (`Some(required_string)` только для source-type adaptation) | 2 PASS + 1 expected RED: missing string field `file_id`, 183 filtered |
| Modules, optional parser | Два неизменённых controls PASS; после исправления тестового assertion упавший target 1/1 PASS |
| Независимый повтор финальных наборов | Core 3/3 PASS; Modules 3/3 PASS, 183 filtered |
| Существующий hosted activity/results/citations test | 1/1 PASS, 185 filtered |
| Source checks | rustfmt новых tests/DTO, git diff --check, strict forward/reverse patch checks PASS |

Повторные запуски и подслучаи не считаются новыми уникальными tests. Это семь уникальных focused tests: три Core, три Modules и один существующий positive control; не полный suite.

Команды:

```sh
# Core candidate:
python3 scripts/test.py -p proteus-contracts --test file_search_result --offline

# Modules с явно описанной ниже локальной композицией contracts:
python3 scripts/test.py -p model-pack --lib file_search_result_ --offline
python3 scripts/test.py -p model-pack --lib adapters::openai::tests::response_preserves_hosted_activity_results_and_citations --offline -- --exact
```

Проверены старые string values, canonical None/null, strict wrong-type/unknown-field отказ, canonical response JSON round-trip; mixed result order, known/missing/empty-string IDs, полностью пустой result, metadata, answer, usage, nonstream/item/final paths и стабильный message ID. Стабильность generated part IDs не утверждается.

## Точная тестовая композиция

Modules compile-time Core pin остаётся `185225a7103088c444788374ca425d230060f55a`, отличным от Core main. Для локального теста скопирован его contracts crate, изменён только `src/domain/hosted_tool.rs` на candidate. Независимо сопоставлены 102 tracked файла: отличается один. Остальные Core crates остаются на штатном pin. Это исключает несвязанные app_protocol изменения между pin и main.

Локальный Cargo patch направлял только `proteus-contracts` на эту копию; lock менял только её source identity. Это test composition, не dependency upgrade и не deployable installation. Overlay/config/lock в опубликованные patches не входят. Штатный Modules runner делает locked metadata lookup, затем locked/offline cargo test; полностью сетево-изолированный workflow не заявляется.

## Исправления собственных tests

Первый Core candidate запуск обнаружил неверный fixture: строку provider status вместо canonical enum JSON. Fixture исправлен через `HostedToolStatus::Completed`; правильный baseline повторён перед финальным GREEN. Первый Modules positive test чрезмерно сравнивал целые CanonicalMessage с заново создаваемыми part IDs; assertion исправлен на stable message ID и payload, затем повторён target. Reviewer отдельно повторил все финальные scoped tests. Эти два test-authoring failure не считаются product defects.

## NOT RUN

Полный Rust DTO gate, Core transcript unit target, affected client builds/UI, journal cold reload, process/module-swap/conformance, deployed pins, packaging и CI. Пустые GitHub check/status lists не являются PASS. HOLD/process/security направления не открывались.

Core patch forward-check выполнен в checkout с дополнительными config-only commits; все три существующих target preimages отдельно сверены с exact `cdf4aa5` и совпадают. Modules forward-check выполнен на unchanged `b7e3ca3`. Оба reverse-check выполнены на candidate trees. Это source applicability, не integration acceptance.
