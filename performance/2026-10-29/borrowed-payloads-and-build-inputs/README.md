# Меньше копирования и корректная инкрементальная сборка

Семь новых source-only patches для актуального фундамента Proteus. Они не
добавляют второй runtime, persistent cache или общий compatibility layer.
Авторский и независимый source review выполнены; **код, тесты, сборки, UI,
CI и benchmarks не запускались**. Static application не является compile pass.

## Базы и применение

- Core: `925de0fc5ee5995409b11e42b216a15ca12f76d0`.
- Modules: `8ec681b861d290d1bcf0d9d9b3087bb463dfd9b2`.
- Desktop: `f822296a47f65c6e1fdeefd7211fbfbc6a6f2294`.
- Extensions: `93d2d98362ea67da0da99043132f0288e65adf72`.

В `SOURCES.json` находятся точные upstream blob hashes, исходные URL,
standalone candidate hashes и результат совместного применения. Применяйте
patch из соответствующего каталога **в его upstream checkout**, начиная с
`git apply --check`. Этот delivery repository сам по себе не обновляет приложение.

Предыдущие schema-cache/history-index/request-ownership/query-scoring/
Arc-content/compact-diff/cache-counter изменения уже перенесены в свежие
upstream commits. Не применяйте их второй раз из PR58/59.

Девять предыдущих патчей PR60 по-прежнему отдельны:
[incremental-work](../incremental-work/README.md) и
[catalog-and-folded-ui](../catalog-and-folded-ui/README.md). Для свежих баз
заменены два старых delivery patch, а не добавлены параллельные варианты:
Markdown process regressions согласованы с новыми math/source-preview tests;
Desktop all-folded regression получил обязательный `timestamp_ms: None`.
Core token cancellation → async ACK по-прежнему применяется именно в таком
порядке. Новые патчи не заменяют эту пару.

## Что убирается

### Core: borrowed transcript parts

`core/01-borrowed-transcript-parts.patch` убирает deep clone всего canonical
message перед выбрасыванием уже виденных и скрытых частей. Renderer получает
borrowed filtered iterator, текст до окончательного join остаётся `&str`.
Все seen-part/call/result side effects, порядок images/tools/citations и
timestamp lookup по исходному, ещё не отфильтрованному message сохранены.
Owned данные итоговых UI rows по-прежнему создаются. Это **не** устранение
полного journal replay. Четыре regression sources охватывают mixed parts,
all-filtered identity consumption, rehosted timestamps и hosted citations.

### Core: notification byte accounting

`core/02-notification-byte-count.patch` считает размер notification payload
тем же compact serde_json serializer без выбрасываемого encoded `Vec<u8>`.
Полный обход сохраняется; нет раннего quota cutoff или частичной длины при
ошибке. Error sentinel, representable-length overflow, validation order,
notification frame/byte budgets, permit/drop и terminal routing остаются.
Это не IPC encode-once и не изменение admission. Тестовые исходники покрывают
UTF-8/escaping, errors, permit lifetime и точную границу quota в broker fixture.

### Modules: checkpoint context anchors

`modules/01-checkpoint-context-anchor-sweep.patch` заменяет повторные поиски
по хвосту model history и canonical ACK на временный набор принятых IDs и
один обратный проход. Request-only контекст сохраняет исходный порядок у
первого следующего retained anchor; trailing context остаётся в конце.
При отсутствии такого контекста сразу возвращается canonical snapshot.
Набор живёт только в этом вызове, не заменяет ACK authority или rollback.
Это ожидаемо линейная организация поиска с дополнительным временным набором
IDs, а не доказанное ускорение или гарантированное уменьшение RAM. Исходники
regressions проверяют old-scan parity, reorder/drop/duplicates и root ACK.

### Desktop: lazy diagnostic accounting

`desktop/01-lazy-history-diagnostics.patch` передаёт подсчёт retained payload
как `FnOnce`: при выключенном `PROTEUS_STARTUP_TRACE` рекурсивный диагностический
обход rows/tool JSON не выполняется. Обязательный history-cache accounting
не меняется; при включённом trace JSON и однократный подсчёт прежние.
Три regression sources проверяют disabled/enabled/once-only paths.
Существующий native-history стенд включает trace и потому **не измеряет**
этот выигрыш обычного запуска; это прямо отмечено в его руководстве.

### Extensions: owned Content ingress

`extensions/01-owned-content-ingress.patch` перемещает language/source/context
из уже принадлежащего SDK входного `Value`, вместо глубокого копирования.
Language-before-source validation, session transition до validation,
сохранение старого Content при ошибке, view/revision/context routing и close
lifecycle сохранены. Пять regression sources включают pointer identity и
ошибку content на смене session. Общий render fan-out не пропускается:
расширения могут зависеть от session events и свежих settings.

### Core и Desktop: Git inputs для build.rs

`core/03-build-ref-watch.patch` и `desktop/02-build-ref-watch.patch` исправляют
одинаковую причину повторного запуска build script: после `git pack-refs`
loose branch ref может отсутствовать, а Cargo считает отсутствующий
`rerun-if-changed` input устаревшим при каждом запуске.

Вместо отсутствующего ref отслеживаются ближайший существующий каталог
в пределах Git refs и существующий packed-refs; это сохраняет обнаружение
следующего loose commit. Для reftable учитываются существующие shared и
worktree stores. HEAD, detached/worktree behavior и no-Git path сохраняются.
Соседний ref в наблюдаемом каталоге может консервативно вызвать пересборку;
весь `.git`, objects, target или workspace не наблюдаются.

Это условный дефект для соответствующего состояния Git, **не** утверждение,
что у владельца именно он вызывает медленные сборки. Обычный release,
выбор компонентов, compiler flags и link profile не меняются. Шесть regression
сценариев в каждом репозитории используют маленький offline Cargo fixture,
но здесь не исполнялись. Общего нового build framework нет.

## Проверка и следующие границы

Root независимо сверил затронутые preimages с Git trees закреплённых commit,
проверил standalone patch→candidate bytes, strict whitespace/application,
совместное применение всего PR60 на свежих базах и точный обратный возврат.
Перед применением на более новых commits нужна повторная проверка: чистый
`git apply` сам по себе не ловит новые обязательные поля DTO, что показал
`timestamp_ms` в старом Desktop regression.

Количественных latency/CPU/RSS/PSS или build-time обещаний нет. Выполняемый
validation gate остаётся в существующих guides каждого upstream. Новые
правила внесены туда, где меняется код, без ещё одного общего свода правил.

Полный incremental journal projection требует не только call-ID dependency:
late citations меняют старые hosted cards, images могут заменить старый row
с тем же MessageId, replacement/compaction меняет видимость и даты. Без
committed cursor, полного dirty-row dependency mapping и strict rebuild
fallback подменять full replay коротким identity check нельзя. SQLite уже
пропускает unchanged SQL writes; её существующую оптимизацию не дублируем.
