# Проверенный patch документации Proteus Core

Это доставка patch в `Qweasd123tg/proteus-modules-dot`, **не merge и не изменение upstream Core**.

- Исходный репозиторий: [Proteus-harness/Proteus-core](https://github.com/Proteus-harness/Proteus-core).
- База: [`bf3af030dd0a6c7323d067f95098319252eef14a`](https://github.com/Proteus-harness/Proteus-core/commit/bf3af030dd0a6c7323d067f95098319252eef14a), актуальный `main` при повторной проверке 5 ноября 2026 года, 09:08 UTC.
- Локальный исходный commit: `68432ac5d0d0a5c4f04efc4cfd5bb0de41c877a3`.
- Артефакт: [`core-docs.patch`](core-docs.patch), полный `git format-patch`.
- SHA-256 файла: `aa6994bba75f449103c9ac353908124b35dbc716e942fee2adc86be319c4fb8f`.

## Состав

Только `README.md`: 12 добавленных и 6 удалённых строк.

1. Описание установки согласовано с `install.sh` и сборщиком модулей: независимые production-модули, две устанавливаемые команды, aggregate reference module только как тестовый fixture.
2. Несуществующий флаг Desktop `--fast` заменён на первую полную сборку `--full` и отдельное обновление Desktop через `--no-archive` с готовой базой. Добавлена ссылка на `BUILDING.md`.

Команды Desktop сверены с `scripts/portable.py` и `BUILDING.md` в [Desktop `6e66189b50c112cf13448fc1feaa1eee5a3c85d6`](https://github.com/Proteus-harness/Proteus-desktop/tree/6e66189b50c112cf13448fc1feaa1eee5a3c85d6).

## Проверки

Успешно выполнены на указанной базе:

- `git apply --check` перед применением и `git apply --reverse --check` после него;
- `git diff --check` и `git show --format= --check HEAD`;
- проверка точного состава diff, ссылок и заголовков назначения;
- сверка утверждений с `install.sh`, `scripts/build_module.py` и указанными исходниками Desktop;
- проверка чистого рабочего дерева после локального commit.

Cargo, portable-сборка и runtime-тесты не запускались: patch меняет только документацию. Эти проверки не заявлены как пройденные.

## Применение

В отдельной чистой рабочей копии Core на указанной базе:

```sh
git apply --check /path/to/core-docs.patch
git am /path/to/core-docs.patch
```

Перед переносом на другую ревизию повторно проверьте применимость и актуальность утверждений. Commit после `git am` может иметь другой SHA из-за metadata коммиттера.
