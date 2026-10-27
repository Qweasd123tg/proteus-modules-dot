# DCP Runtime Packaging — Изолированный Эксперимент

Источник: Proteus-harness/Proteus-modules, строго
`0d9c5fd18f04e6e3a083351678065c5f72966792`.
Этот каталог — переносимый source patchbundle, а не готовый зарегистрированный
module и не обновлённый portable release. Upstream не изменяется.

## Что Меняется

- DCP 3.2.0 становится build/dev dependency, tokenizer 0.0.4 — прямой production
  dependency. Все 174 зафиксированные npm resolutions остаются прежними.
- Новый stage копирует исходники и зависимости в отдельный отсутствующий каталог,
  сохраняет соответствующие источники DCP, licenses, full lock, esbuild metafile
  и embedded-package inventory, затем делает offline production prune.
- Сохраняются полные tokenizer, tiktoken 1.0.22, @types/node 18.19.130 и
  undici-types 5.26.5, включая WASM. Проверка сравнивает все сохранённые файлы
  в обе стороны, обнаруживая удаления, добавления и изменения.
- Лицензия plugin 1.18.35 отсутствует в npm tarball: приложена точная официальная
  release license с pinned source/hash, без утверждения о npm gitHead.
- Zod 4.1.8 остаётся внутри JS bundles. Это не исправление advisory; никаких
  обновлений Zod, TOML или поведения DCP в этом эксперименте нет.

## Применение Без Изменения Исходного Checkout

Нужен чистый checkout указанного полного SHA. Контроллер проверяет whole-bundle
hash, каждый original Git blob, UTF-8 byte count и SHA-256 новых файлов.
Он экспортирует закреплённые Git objects и публикует целиком готовое дерево
атомарным rename в новом `/new/output/tree`.
Исходный checkout и существующие назначения не перезаписываются.

```sh
python3 -B -I apply.py \
  --source /clean/Proteus-modules \
  --bundle source-bundle.json \
  --sha256 ac057dd37a05a3c0540f288698f431fd45c64dbc5f21d9365048ce1ac58914ba \
  --output /new/output
```

Полные инструкции внутри результата: `hook/dcp/packaging/README.md`.

## Проверка

На момент авторства выполнены только in-memory hash/readback проверки и
read-only синтаксический разбор Python/JavaScript. Сборки, npm install,
runtime tests и hosted gate здесь не запускались. Независимое ревью проверяет
те же exact bytes; результат фактического hosted run хранится отдельно.

`.github/workflows/dcp-runtime-packaging.yml` запускается только
для точной ветки `ci/dcp-runtime-packaging-20261027` в
Qweasd123tg/proteus-modules-dot, с path filters и job guard. Нет main/PR/schedule
triggers, writes, releases, merge или upstream CI changes. Один Linux x64 job,
20 минут, Node 22.23.4, Python 3.12.15, contents: read, без persisted credentials.

Gate очищает дочернее окружение от credentials, отключает npm audit/lifecycle
scripts и проверяет: baseline/candidate JS hashes; исходные tests; complete
runtime closure; перенос под независимый /tmp root; direct tokenizer/WASM и
реальный worker protocol; потерю WASM, ненулевой worker exit и поздний malformed
stdout как отрицательные контроли; tests с обоими pinned Core harnesses
f3d01053 и shipping 63454d4. Сохраняются commands/exit codes и before/after
inventories. Никакого npm advisory POST, включая retry или splitting.

Исходный PR30 npm tree содержит 147573160 bytes вне четырёх runtime packages.
Это opportunity, не полученная экономия. Actual net delta должен учитывать
новые source/license/provenance overhead. Даже успешный Node gate не доказывает
готовность shipping portable: отдельный consumer rebuild/launcher gate остаётся
обязательным, а недоступный desktop этим bundle не редактируется.

## Дополнение По Runtime Notices

Выявленные отсутствующие MIT notices tiktoken 1.0.22 и undici-types 5.26.5
сохранены отдельно в provenance по точным registry gitHead официальных
репозиториев; package bytes/versions и WASM не меняются. Новые tests отклоняют
отсутствие, подмену и version mismatch; hosted gate проверяет все четыре
runtime package notices и сохраняет тексты в evidence. Это не общее правовое
заключение. Размеры прошлой проверки head 043770 относятся к прежнему набору;
размеры дополненной версии устанавливаются отдельным новым run.
