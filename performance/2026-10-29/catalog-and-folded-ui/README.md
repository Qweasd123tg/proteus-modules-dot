# Каталоги без ненужных копий, свёрнутый UI без обхода

Три узких source-only патча, дополняющих [предыдущий пакет](../incremental-work/).

- **`modules/01-schema-byte-count.patch`**: token estimate selector-а использует тот же compact JSON serializer, но считает bytes через private Write вместо выделения полной строки каждого ToolSpec. Сохраняются per-tool floor(bytes/4), skip serialization errors, сумма и metadata before/after. Это прежняя оценочная конвенция, не точный tokenizer. Capacity overflow не превращается в тихое насыщение/пропуск; потребность в полном временном JSON buffer удалена, одинаковое поведение при исчерпании памяти не обещается.
- **`modules/02-skill-metadata-no-body-copy.patch`**: provider/catalog native skill-pack не создают ненужный owned body. Полный ограниченный read, UTF-8/YAML/path/name/size validation, настройки, warnings, precedence и свежий discovery сохранены. Tool load по-прежнему получает полный body. Нет TTL, второго каталога, persistent cache или пропуска чтения файлов.
- **`desktop/01-empty-expanded-diff-preparation.patch`**: если нет развёрнутых строк, prepare_tool_diffs сразу возвращается вместо обхода transcript. Старый loop не имел эффектов в этом случае; cleanup остаётся в прежнем owner. При наличии раскрытых строк подготовка, source comparison и lifecycle не меняются; DiffView при folding по-прежнему удерживается.

Desktop regression обновлён под обязательный `timestamp_ms`; production guard прежний. [Следующие семь патчей и общая сверка](../borrowed-payloads-and-build-inputs/README.md).

## Применение и ограничения

Точные refs, Git blob identities и контрольные суммы находятся в `SOURCES.json`/`SHA256SUMS`. Папки относятся к отдельным upstream checkout. Проверить `git apply --check --whitespace=error-all <patch>`, затем применять; внутри папки порядок числовой. Базы обновлены до свежих commits из SOURCES.json; соответствующие #58/#59 уже upstream, повторно их применять не нужно. Совместное применение всех 16 текущих патчей PR60 проверено статически. Upstream-репозитории этим delivery commit не изменяются.

Авторское и независимое source review, baseline hashes, strict whitespace, patch application и candidate byte checks выполнены. Добавлены unrun regression sources для JSON byte/rounding/error parity, skill metadata/error/freshness parity и выбора актуального patch source после snapshots. Последнее **не является** проверкой GPUI render/unfold/animation: native UI сценарии остаются непроверенными.

**Rust, tests, builds, UI, CI, benchmarks не запускались.** Static apply не подтверждает компиляцию или runtime. Нет новых чисел latency/CPU/RSS/PSS. Общие правила разработки уже закреплены в существующих upstream guides патчами предыдущих пакетов; отдельный дублирующий свод не добавляется.

## Что нельзя безопасно упростить ещё одним локальным shortcut

**Dirty gate Desktop.** `Transcript::same_tool` сравнивает наличие effective_args, а не все args/name. Snapshot/reconnect может заменить patch при стабильном row key и Change::None. Поэтому более сильный cache по length/key/change сейчас небезопасен; действующая проверка актуального source при раскрытой строке сохранена. Отдельный пользовательский UI defect этим аудитом не доказан.

**Same-worker typed helpers.** В [module runtime](https://github.com/Proteus-harness/Proteus-modules/blob/ecbf04a68079d9f493c141d63d09ff4014c7823e/components/module-runtime/src/exports.rs) и coding workflow есть JSON roundtrip вокруг link-time Rust helper `WorkflowModule::run_json`, не вокруг in-process extension ABI. Но current from_str — fallible normalization/depth boundary: deeply nested output metadata может сериализоваться и затем отклоняться parser-ом. Прямой typed bypass удалил бы этот transport error; ошибки serialization внутри реализации сейчас попадают в WorkflowFailure и имеют другой lifecycle. Также нужно сохранять defaults, None/Some([]), path/float/Value semantics.

Корректное изменение требует согласованной замены существующего helper trait и всех четырёх реализаций/внешних callers, без compatibility-дубля и без slot-specific обхода runtime. Modules сейчас закреплён на реальном Core `1f533a13f20a93bf164f7c8a169553b0b219bb51`: сначала нужен опубликованный Core revision с новой API, затем намеренное обновление dependency/lockfile и consumer checks. Несуществующий SHA и бессвязный bump к HEAD не подставлены. Host callback helpers затрагивают ещё workflow/hook/tool и не должны автоматически включаться в тот же migration. Ни production patch, ни dependency bump по этому направлению здесь нет.
