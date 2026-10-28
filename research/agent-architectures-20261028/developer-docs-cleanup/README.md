# Очистка документации после standalone-перехода

Подготовлены **два source patches**, без изменений runtime, installer, test runner,
CI или значений config. Исходные репозитории использовались только для чтения.

| Patch | Source pin | Scope |
|---|---|---|
| [Modules](patches/modules-developer-docs-cleanup.patch) | `Proteus-harness/Proteus-modules@ea459a60d8fce621ccabff33ff7ff9dc9d55573a` | 2 документа |
| [Core](patches/core-developer-docs-cleanup.patch) | `Proteus-harness/Proteus-core@bd4aae62c738befcdf9b3a1a831837447ecb7aad` | 13 документов и комментарий example config |

## Что исправлено

- Installer docs больше не обещают устанавливаемый aggregate executable:
  фактическая поставка — Core + самостоятельные workers в `bin/` и metadata
  в `share/modules/`; публичные launchers — `proteus` и model-pack auth.
- Source-run пример действительно подготавливает пакеты, которые требует
  `proteus.example.toml`: `build_module.py --bundle`, абсолютный destination
  и соответствующий `PATH`. Без `--bundle` helper собирает только fixture.
- Portable-команда использует release по умолчанию, не `--fast` для сравнений
  runtime/RAM. Семантика проверена по Desktop
  `010b949b41f9a0349e4c64280872fe8e31f403de`: обычная команда собирает release
  и архив; `--fast` выбирает другой профиль клиента без LTO и пропускает архив.
- Рабочие config snippets используют правильные standalone executable/export
  пары; multi-export возможность protocol не удалена. Намеренные aggregate
  wire/topology/conformance примеры сохранены с явной маркировкой fixture-only.
- Test commands разделены по Core/Modules workspace и используют существующий
  runner, который подготавливает pinned harness и нужные artifacts. Никакие
  тесты в рамках этой правки не запускались.
- Modules README стал одной точкой входа для разработки: отличает package ID
  `plan-tool`, implementation Cargo package `plan-tool`, executable/Cargo package
  `proteus-plan-tool-module` и export `tool/plan_tool`; ссылается на manifests
  и `exports.json`, не создавая ещё один вручную поддерживаемый реестр.
- Повторяющийся абзац про равные права reference/external modules сведён к одному.

## Статическая проверка

- Все 16 оригиналов сверены по Git blob SHA с GitHub connector; pins и hashes —
  [source-pins.json](source-pins.json).
- Все 10 изменённых TOML-блоков разбираются; standalone commands и exports
  сверены с 18 текущими `exports.json` Modules.
- Изменение `examples/configs/proteus.example.toml` затрагивает только комментарий:
  разобранные TOML-значения до/после равны.
- Новые локальные ссылки и anchors проверены; cross-repository navigation
  ссылается на добавляемый раздел Modules README, поэтому применять нужно оба patch.
- Оба patch проходят `git apply --check --whitespace=error-all` на исходных pins.
  Полная запись проверок — [static-review.txt](static-review.txt).

Это **не** evidence запуска приложения, installer, build, test или CI.
Локальную поведенческую проверку выполняет пользователь. Существующие корректные
fixture references, исторические материалы и upstream provenance не переписывались.

## Применение

Применять каждый patch в соответствующий отдельный checkout на указанном pin,
сначала проверить `git apply --check /absolute/path/to/PATCH`, затем `git apply`.
Не применять Core patch к Modules workspace или наоборот. При другом HEAD сначала
пересмотреть контекст: совместимость с будущими исходниками не заявлена.

