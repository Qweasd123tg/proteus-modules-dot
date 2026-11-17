# Одно разрешение выбранного model alias

Локальный source-кандидат Core, без публикации и применения к upstream.

## Что убрано

В `core/config/models.rs::normalize` alias сначала искался через `contains_key`,
а после настройки bindings повторно искался через `ModelScope::selected_model`.
Теперь существующий `selected_model()` вызывается на месте первого guard.
Он по-прежнему отклоняет неизвестное имя и возвращает нужную конфигурацию;
отдельный предварительный guard удалён. Один файл: **+1/−5**.

Это устраняет один повторный BTreeMap lookup на выбранный alias в каждом
нормализуемом scope. Замеров latency/RSS нет; ускорение приложения не заявлено.
Новых helpers, caches, тестов и wrappers нет. Существующие тесты не удалены.

## Почему ошибки сохраняются

- До прежнего первого guard присваиваются те же `scope.selected` и `presets`.
  Для неизвестного имени `contains_key` и `get(...).with_context(...)`
  возвращают тот же текст `unknown model alias ...`, до тех же мутаций документа.
- Между прежними двумя проверками `inherit_bindings` читает `presets`, а
  `capture_bindings` меняет только `components/settings`. Выбор не меняется,
  `await` и внешнего изменения данных между ними нет.
- `ProviderProfileConfig::to_model_config` в закреплённой версии только клонирует
  поля в `Ok(ModelConfig)`. Поэтому перенос не меняет порядок recoverable errors.
  **Если туда позже добавят fallible validation, порядок ошибок потребуется
  пересмотреть.** Публичный `Result` намеренно не менялся: его caller находится
  также в исключённой process-области.
- Нормализация child scope и исправление child-local alias из #171 не менялись.
  В отличие от удаления guard без переноса lookup, неизвестный alias не
  откладывается до проверки bindings.

## Проверка

База Core: `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`, текущий upstream `main`
повторно подтверждён через GitHub. Dot snapshot сверён до merged #181
`99b88e2dd2be8d38a2d407756cfd903ed49de990`: аналогичной чистки там нет,
#181 занимается другим повторным сравнением в persistence.

Native Rust/Cargo 1.95.0, `--offline --locked -p proteus-core --lib`:
**те же 12 существующих model/inline tests PASS до и после** (24 исполнения,
не 24 уникальных теста). Покрыты root/nested selection, локальные каталоги,
explicit child route, неизвестные имена, неоднозначные источники и malformed
presets, inline references и instructions. Список имён сохранён в verification.json.

```sh
cargo test --offline --locked -p proteus-core --lib -- \
  core::config::models::tests core::config::inline_tests --test-threads=4
```

Direct Cargo вместо Core runner ограничивает выполнение чистыми config tests;
runner для любого `--lib` готовит process module fixtures. Никакой worker или
AgentAppServer не запускался. Два существующих dead_code warning profile polling
одинаковы в baseline и candidate.

Targeted Rustfmt, `git diff --check`, strict forward/reverse apply и точное
восстановление bytes: PASS. Cargo.lock неизменён. Независимый source-review:
ACCEPT, с той же оговоркой о будущей fallibility.

Совместимость с combined #167/#171: strict patch apply поверх `b2c285f`
и отдельный native прогон тех же config filters: **15 PASS, 0 FAIL**, включая
три существующих regression methods #171 (child-local alias, shadowing и
неизвестный внешний alias). Это ещё 15 исполнений; суммарно 39 исполнений
15 уникальных methods, не 39 уникальных tests. Persistence-target #167 в этом
проходе не повторялся, его полная квалификация не заявляется.

Full workspace, process/security/isolation, hosted CI, portable и benchmarks
не запускались. Production contracts/API, persistence и HOLD не изменены.
Другие похожие guards и schema tests оставлены: доказанного безопасного удаления
в этом проходе для них нет.

Локальный commit: `6a3eca9f7f8bca3969bd8da11c9b0c755a92405d`.

## Порядок применения и другие proposals

Patch автономен: исходная база `cdf4aa5`, зависимостей от предыдущих fixes нет.
После combined #167/#171 (`b2c285f`, опубликованная квалификация #175) он
применяется напрямую; описанный выше native прогон проверяет эту композицию.

Дополнительно на чистой базе проверено строгое применение в **обоих порядках**:
этот alias patch + #181 `model-comparison-once.patch`, а также alias patch +
standalone source/regression patches `inline-model-settings-ownership` из **#177**.
Для каждой пары итоговые bytes полностью совпадают. Это только apply/source
проверка, не новый совместный runtime-прогон. Эти fixes меняют persistence,
а alias patch меняет только `core/config/models.rs`.

Не применять raw #167/#171 повторно поверх combined пакета #175. Варианты
inline-settings из #177 остаются альтернативными согласно их README;
алиасная чистка не устраняет существующие конфликты между другими proposals.
В частности, #181 уже документирует необходимость rebase на composed #167.
Общий runtime-pass для цепочки всех этих proposals не заявляется.
