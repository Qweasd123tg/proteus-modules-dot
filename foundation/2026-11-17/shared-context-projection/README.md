# Общая проекция ContextChunk для JavaScript model adapters

Дата: 17 ноября 2026. **Проверенный ограниченный кандидат для Modules, не
интеграция upstream и не qualification полного продукта.**

## Реальная проблема и один владелец

В Modules `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7` новый OpenCode model bridge
передавал только `ContextChunk.content`, теряя `source` и `path` независимо от
`render_mode`. Это нарушает действующий
[контракт Core](https://github.com/Proteus-harness/Proteus-core/blob/185225a7103088c444788374ca425d230060f55a/crates/proteus-contracts/src/domain/context.rs):
`source_annotated` требует `Context from <source> (<path>):\n<content>`, а
`verbatim` сохраняет содержимое без оболочки. Конструктор ContextChunk по
умолчанию выбирает `source_annotated`. Metadata не должна выбирать режим.

[Patch](shared-context-projection.patch) переносит существующее правило Pi в
один чистый helper `components/model-runtime-js/context.mjs`, используемый
обоими JavaScript adapters. Provider-specific message shaping остаётся у
каждого adapter. Новый framework, runtime state, cache, provider alias или
fallback transport не добавляются. Rust formatter не меняется.

- OpenCode теперь сохраняет source/path и различие режимов.
- Pi сохраняет обычное поведение. Явный пустой path `""` теперь означает
  присутствующий пустой путь `()`, как `Some(PathBuf::new())` у Rust, а не
  отсутствие path. Это небольшое намеренное изменение, не заявление полной
  побайтовой эквивалентности старому Pi.
- Содержимое, Unicode, CRLF/LF, пустые строки и порядок частей не нормализуются.
  Input DTO не меняется; metadata не управляет отображением.
- Входной contract по-прежнему валидирует Core. Этот helper не вводит новый
  compatibility reader или самостоятельную систему проверки DTO.

Изменены три production-файла, включая новый семистрочный helper; сохранены
15 существующих OpenCode IO tests и добавлены две проверки фактических
потребителей. Два теста содержат по шесть одинаковых граничных случаев, это
**не двенадцать уникальных тестов**. Старый минимальный Context fixture теперь
явно задаёт обязательные canonical поля и `verbatim`, сохраняя прежние assertions.

## Что действительно запущено

Точные источники и pins: [SOURCES.json](SOURCES.json).
Dependencies установлены штатным `npm ci --ignore-scripts` по неизменённому
upstream lock. Все **395 установленных package-lock records** совпадают по
version/resolved/integrity. Использован закреплённый **Node 24.12.0**,
`@opencode/ai 2.0.22`, Effect `4.0.0-rc.112`.
Это сверка lock records, не отдельное хеширование каждого установленного файла.

| Проверка | Результат |
|---|---|
| Исходный неизменённый OpenCode IO suite | 15/15 PASS |
| Новые regressions на исходном production-коде | 15 PASS, 2 ожидаемых FAIL |
| Candidate: OpenCode IO + чистый Pi consumer test | 17/17 PASS, без skipped |
| Независимый повтор candidate тем же Node | 17/17 PASS, без skipped |
| Strict patch apply, reverse и точное восстановление исходных файлов | PASS |
| Обе существующие installer source-copy loops и imports из изолированных layouts | PASS в ограниченном scope ниже |

Baseline OpenCode теряет четыре annotated оболочки; baseline Pi отличается
только на пустом, но присутствующем path. Проверки проходят через реальные
`toNativeRequest`/native `LLMRequest` и `piMessages`, а не Python-переписывание
их поведения. Они проверяют также metadata-противоречия, verbatim bytes,
optional/empty path, empty content, surrounding parts и отсутствие мутации.
Независимое review не нашло блокеров: [REVIEW.md](REVIEW.md).

### Packaging boundary

Оба существующих installer уже копируют `components/model-runtime-js`.
В изолированных временных layouts были исполнены **только неизменённые
source-copy loops**, извлечённые из их AST, без installer main, npm subprocess,
launcher или запуска worker. Затем обе consumer import chains вернули
ожидаемую annotated строку. OpenCode dependency directory при этой проверке
ссылалась на описанную exact-lock установку.

Это проверка **source-layout/import closure**, не полный install/portable,
архив, запуск binary, RPC или пользовательская установка. Новая production
зависимость находится в уже существующем packaging family; installer менять
не требуется. Pi workflow/compaction также использует `piMessages` в том же
сохраняемом расположении. Частичное materialization checkout не объявляется
полной сборкой Modules.

## Воспроизведение focused gate

На чистом Modules checkout точной базы проверьте и примените patch. Затем:

```sh
cd workflow/opencode-runtime
npm ci --ignore-scripts --no-audit --no-fund
cd ../..
workflow/opencode-runtime/node_modules/node-linux-x64/bin/node --test \
  model/opencode-provider/tests/io.test.mjs \
  tool/pi-tools/tests/context-rendering.test.mjs
```

Чтобы увидеть baseline failure, примените только два test-file hunks к чистой
базе и выполните ту же команду. Не добавляйте helper/production hunks до этого
контроля. Candidate целиком даёт 17 PASS; tests-only baseline даёт 15 PASS и
2 FAIL. Новая Pi проверка автоматически входит в существующий
`tool/pi-tools/package.json` glob, OpenCode проверка остаётся в своём IO suite.

## Границы вывода

**Не запускались:** full Pi/OpenCode npm suites, process/HTTP/provider/auth
fixtures, настоящий Core, Rust/Cargo, полный installer/portable, native UI,
hosted CI и benchmarks. Платных model calls не было. Исключённые
process/security scopes не трогались. Ускорение или снижение RAM не заявляются.

Локальные focused PASS не означают CI PASS или readiness всего продукта.
Перед upstream adoption остаются обычные affected package/installer и
интеграционные gates в разрешённом окружении. Этот пакет не меняет upstream,
consumer pins, активные workflows, binaries или установленный Proteus.

Порядок InstructionBlock.priority, глобальная история tool-call IDs и
терминальная семантика collector не меняются и не считаются исправленными
этим patch. Исторические #165/#166 и уже принятые #86–164 не переупакованы
и не предлагаются к повторному применению.
