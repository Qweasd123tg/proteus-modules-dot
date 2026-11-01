# Сохранение выключенных подсказок при миграции

Патч для `Proteus-harness/Proteus-desktop` на commit
`722b150f2af5c9374081272ca402189666c77bbc`.

Старые строковые настройки `hints: "off"` и `hints: "keys"` переносились
с новым значением `title: "clipped"`. У кнопок-иконок название считается
обрезанным, поэтому после обновления появлялся tooltip даже при прежнем Off.
Keys мог показывать название вместо только сочетания клавиш.

Исправление задаёт `title: "never"` для Off и Keys. Full и Description
сохраняют прежнее поведение миграции; defaults и новый объект настроек не
меняются. Дополнена существующая таблица migration/roundtrip-теста, без новых
тестовых функций, fixture, настроек или runtime-проверок.

Уже сохранённые настройки нового формата остаются как есть: по ним невозможно
отличить явный выбор пользователя от результата прежней миграции. Патч не
пытается угадывать это и не сбрасывает текущие предпочтения.

## Проверка

- Точный исходный blob сверён с GitHub.
- Strict apply/reverse с проверкой пробелов и побайтным восстановлением выполнен.
- Прямая проверка установленным `rustfmt` пройдена.
- Rust/Cargo-тесты, приложение и CI не запускались. Это source-пакет, не
  подтверждение нативного поведения. Следующая проверка: существующий тест
  `saved_tooltip_modes_migrate_without_losing_other_preferences` и hover
  кнопки-иконки после загрузки старых Off/Keys preferences.

Источники: [старое поведение Off/Keys](https://github.com/Proteus-harness/Proteus-desktop/blob/a28cc7f507424a570e86dc44230ee323156fdf6c/src/ui/kit.rs#L236-L244),
[исходная миграция](https://github.com/Proteus-harness/Proteus-desktop/blob/722b150f2af5c9374081272ca402189666c77bbc/src/preferences.rs#L576-L599),
[название у кнопки-иконки](https://github.com/Proteus-harness/Proteus-desktop/blob/722b150f2af5c9374081272ca402189666c77bbc/src/ui/kit.rs#L303-L312).

Из корня соответствующего Desktop checkout: `git apply --check legacy-tooltip-migration.patch`,
затем `git apply legacy-tooltip-migration.patch`. Исходный репозиторий этим
пакетом автоматически не изменяется.
