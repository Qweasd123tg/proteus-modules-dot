# Как повторить проверки

Нужны исходные деревья [Desktop](https://github.com/Proteus-harness/Proteus-desktop/tree/2307e9c67125bbe66f15ced51317a2dfcc437aa4), [Core](https://github.com/Proteus-harness/Proteus-core/tree/c2cbadee518788f306ffb2b5271036b2658ea8cc), [Modules](https://github.com/Proteus-harness/Proteus-modules/tree/0fe8e3b4dfb64ca2e07df8af016d7ccc3a7de45f), [Extensions](https://github.com/Proteus-harness/Proteus-desktop-extensions/tree/ef064381d2194d95faef2b85f6cc3a1c34c6b975). Отчёты проверяют структуру данных, правила выбора и видимость состояний, а не реальную установку или доступ к памяти.

Из этого каталога или с соответствующим префиксом в имени скрипта:

1. **Официальные компоненты.** `python3 official_inventory.py "$MODULES" "$EXTENSIONS" "$DESKTOP" "$CORE"` для Git-копий с указанными объектами. Используются только Git show/grep по фиксированным публичным файлам и декларации имени инструмента. Результат: [official-inventory.txt](official-inventory.txt).
2. **Существующий профиль.** `python3 static-check.py "$CORE" "$MODULES"` (Python 3.11+). Проверяются Git blob ID четырёх файлов; отдельно вычисляется иллюстрация замены массива, не запускается загрузчик Core. [Результат](receipt.json).
3. **Модель каталога.** `python3 catalog_shape.py --desktop "$DESKTOP" --modules "$MODULES" --extensions "$EXTENSIONS" --deps /path/to/deps`. В deps нужны совместимые rlib serde (с derive) и serde_json; для нескольких вариантов передайте `--serde` и `--serde-json` явно, компилятор можно задать `--rustc`. Компилируются исходные Rust-типы из закреплённого Desktop, не обработчики или команды из описаний пакетов. [9 индексов, 47 записей](catalog-output.txt) и [независимый контроль неизвестных типов и полей](independent-catalog.txt).
4. **Видимость состояний.** `python3 verify_catalog_ui.py "$DESKTOP" "$MODULES" "$EXTENSIONS"`. Проверяются исходные условия формирования строк, подписи действий и записи обоих каталогов; окно и клики не эмулируются. [Результат](ui-observed.json).

Примеры с именами `bundle`, `members`, `requires` нужны, чтобы проверить поведение нынешнего формата. Они заведомо не являются устанавливаемыми пакетами и не предлагаются как готовая спецификация.
