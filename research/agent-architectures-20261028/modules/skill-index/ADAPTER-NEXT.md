# Подключение portable skill search

[Исходниковый tool/v6 adapter уже подготовлен](../../runtime-fixes/skill-search-adapter/README.md).
Это отдельный patch для `examples/portable-skill-catalog`; он ещё не применён
к примеру автоматически и не проверен исполнением.

Каждый вызов использует свежий `discover`, строит metadata-only индекс и
возвращает точные `load_args`. Дополнительного cache или общего состояния
между процессами нет. Включение — через allowlist host; исходный профиль
не меняется. Новый профиль явно помечен legacy SDK/Core `3f36a003` fixture,
а не конфигурацией текущей standalone-поставки.

Сборки, tests и CI не запускались. Требуемый crate находится в этом каталоге;
SDK pin и независимая проверка `portable_skill_load` сохранены.
