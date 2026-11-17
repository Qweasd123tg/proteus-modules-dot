# Inline-роли: сохранять владельца модельных настроек

Новая ошибка Core `cdf4aa5`: сохранение других настроек inline-роли с частичным
`module_config.model` незаметно копировало в неё настройки родителя. После этого
изменения родителя переставали доходить до дочерней роли. Реальный Rust reader и
writer воспроизводят проблему в TOML и JSON.

Исправление использует один принцип: если effective модельные настройки не
менялись, сохранять исходную локальную таблицу, включая частичную таблицу или
её отсутствие. Намеренное редактирование настроек и не-inline профили сохраняют
прежнее поведение. Новых API, schema fields и provider-specific правил нет.

## Проверено

- Native baseline: один regression падает на обеих формах, включая последующее
  изменение родителя; не Python-имитация.
- Standalone кандидат: **10 разных focused Rust tests PASS**, из них один новый.
- На композиции с #167/#171 тот же новый regression также PASS, не дополнительный
  одиннадцатый тест.
- rustfmt изменённых файлов, diff check и точная apply/reverse-проверка варианта.
- [Независимый review](INDEPENDENT-REVIEW.md), [полный отчёт](REPORT.md),
  [версии и результаты](VALIDATION.json), [логи](logs/).

Проверка вызывает AppConfig::load и настоящий persistence helper с временными
файлами. App-server Save/publication, watcher, HTTP, модель, process fixtures,
UI, полный workspace и packaged build **не запускались**. Ускорение не заявлено.
Публикация в delivery не меняет upstream и не устанавливает исправление.

## Выбрать один путь применения

1. Для чистого Core `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d`: применять
   `inline-settings-source-owner.patch` и `inline-settings-regression.patch`.
2. После **исходных** #167 production + regression и #171 patches: применять
   **только** `inline-settings-on-PR167-PR171.patch`. Он включает этот fix и его
   regression. Это не обещание применимости после formatted пакета #175.

Эти варианты альтернативны. Обычные patches конфликтовали контекстом в обоих
порядках с #167; отказы сохранены в COMPOSITION.json. Явный rebased вариант
проверен отдельно, без forced/fuzzy применения (VARIANT-CHECKS.json).

Standalone focused команды, Rust 1.95 и уже подготовленные locked dependencies:

```sh
cargo test --offline --locked -p proteus-core --lib app_server::config_builder::tests::model_names:: -- --nocapture
cargo test --offline --locked -p proteus-core --lib app_server::config_builder::tests::inline_roles:: -- --nocapture
```

Старые уже материализованные overrides автоматически не удаляются. Известные
проблемы внешней конкурентной записи и удаления настроек из file includes
остаются отдельными. #137 касался provider definitions, #167 spelling выбора
модели в include, #171 scope локального alias; это не повтор этих находок.
