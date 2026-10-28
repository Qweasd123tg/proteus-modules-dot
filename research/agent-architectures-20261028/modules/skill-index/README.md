# Bounded skill index — самостоятельный Rust-прототип

**Результат:** чистая std-only библиотека ранжирования уже обнаруженных skills.
Она не повторяет importer, snapshot cache, filesystem guards или process host.
Исходники написаны и просмотрены; **компиляция, тесты, benchmarks и CI не
запускались**. Это не установленный Proteus-модуль и не проверенная SDK-интеграция.

## Что добавлено относительно предыдущей работы

`runtime-fixes/portable-skill-catalog-snapshots.patch` из предыдущего пакета уже
добавляет provider-local `Arc` snapshot, revision, single-flight discovery,
30-секундную freshness policy и повторную проверку roots/read guards. Поиска там
нет. Новый `SkillIndex` строит неизменяемые token tables и даёт отдельный
`search`, не добавляя второй cache, watcher или importer.

- До 128 skills: существующий importer limit **не увеличен** до OpenClaw 4096.
- Metadata индексируется прежде всех bodies. Переполнение metadata term budget
  отвергает весь новый индекс, а не незаметно вытесняет последние skills.
- Необязательные body-префиксы получают отдельные byte/count/token budgets.
  Не поместившиеся bodies оставляют metadata-поиск; неполнота отражается в coverage.
- Нормализация: сначала Unicode lowercase, затем alphanumeric words. Каждый
  character из lowercase expansion классифицируется так же, как во входе:
  `İx` и `i\u{0307}x` дают одинаковые lexical terms (`i`, `x`). Combining marks
  служат разделителями, а не сохраняются только в одной из форм. Поддерживаются
  кириллица и Unicode metadata; нет stemming, fuzzy search, embeddings, NFKC или
  полноценного Unicode case folding. Токены длиннее 64 UTF-8 bytes пропускаются
  целиком, не становятся ложными prefix matches.
- Сначала точное имя (`trim`, ASCII-case-insensitive), затем число **разных**
  совпавших query terms, затем сумма весов: name 4 / description 2 / body 1.
  Для каждого терма считается только сильнейшее поле. Повтор слова не усиливает
  rank; все tie-breaks — bytewise ID ascending. Это объяснимый baseline, не BM25.
- Выдача содержит только ID, source, полный digest, score и coverage; не instruction
  body, не path, не permission token. Индекс не пишет model prompt самостоятельно.

## API и authority boundary

`SkillIndex::build(SnapshotKey, &[SkillFacts], Limits)` заимствует уже прочитанные
факты, проверяет lengths/counts до разбора строк, сохраняет ID/source/name/digest
и token vocabulary. Description и сырой body не сохраняются. **Слова из body
всё равно являются содержимым документа**: строить индекс можно только после
допущенного чтения. Отсутствие сырого Markdown не превращает vocabulary в
несекретные данные. `Debug` индекса печатает только key/statistics, не vocabulary.

`search(current_snapshot, &[CurrentSkill], query, result_limit)` каждый раз
требует новый **host-derived** список текущих кандидатов. Adapter обязан сначала
применить immutable settings текущего invocation, config disabled, runtime
disabled, `disable-model-invocation` и нужные read/source guards. Передавать список
из model arguments, сохранённого результата прошлого поиска или mutable UI state
нельзя. Список — данные, не доказательство permission; библиотека не умеет
самостоятельно аутентифицировать вызывающую сторону или проверять OS-grants.

При изменении disabled-набора не нужен authority cache: исключённый ID просто
отсутствует в текущем списке и не участвует ни в hits, ни в search coverage.
Возврат disabled skill через старый `SkillIndex` таким вызовом невозможен.
Это свойство условно на корректную фильтрацию adapter; пользовательский код,
который заново передал запрещённый ID как разрешённый, библиотека не распознаёт.

### Устаревание — явный отказ, не stale-on-error

| Ситуация | Поведение |
|---|---|
| Другой binding epoch или catalog revision | `StaleSnapshot`, без hits |
| Текущий ID отсутствует в индексе | `CurrentSkillMissing`, без partial result; rebuild |
| Текущий source/digest не совпадает | `CurrentIdentityMismatch`, без partial result; refresh/rebuild |
| Duplicate IDs в build/current | Явная ошибка, без зависимости от порядка |
| ID исключён текущими настройками | Даже совпадающий cached token не рассматривается |
| Body отсутствует или пропущен budget | Metadata-only поиск, явная coverage |
| Огромный/пустой query, >32 distinct terms, длинный query token | Явная ошибка, query не обрезается |
| Body prefix обрывается внутри UTF-8 character/word | Безопасная UTF-8 граница; незавершённое слово не индексируется |
| Ошибка нового build | Ошибка возвращается caller; старый индекс не выбирается автоматически |

`SnapshotKey` — host assertion, а не hash или clock. В частности, одинаковый key
**не доказывает**, что файл на диске не изменился. Adapter должен использовать
новый `binding_epoch` при пересоздании export/config/root binding и новую revision
при изменении любых indexed facts. Revision из существующего cache локальна
export и сбрасывается при его создании; без epoch её нельзя переносить между
процессами. Этот прототип не назначает epoch, не выполняет rescan и не продлевает
30-секундную freshness policy предыдущего patch.

Старые metadata/digest до expiry остаются возможны ровно как в исходном cache.
После поиска существующий `portable_skill_load` заново проверяет **текущие**
settings, вычисленный path, full-file SHA-256 и read guards. Changed-file error
требует свежего каталога и нового выбора, не retry старого результата. Digest
относится к полному SKILL.md, не body prefix и не references/assets.

## Конкретные точки интеграции (не реализованы этим пакетом)

1. **Metadata-only, минимальный шаг:** после успешного `discover` либо при
   получении `PublishedSnapshot` создать `SkillFacts` из `PortableSkill`:
   `id`, `source_id = portable:{root_id}`, `fields.name`, `fields.description`,
   строгий decode 64 hex chars `sha256` в `[u8; 32]`, `body = None`.
   Caller-owned epoch + `PublishedSnapshot.revision` образуют key. В примере
   importer ID <=97 bytes, source <=41, name <=64; description <=1024 chars
   помещается в максимальные 4096 UTF-8 bytes этого индекса.
2. **Reuse:** хранить один индекс рядом с тем snapshot **внутри того же export**.
   Успешный rebuild публикует соответствующую пару snapshot/index атомарно.
   Mutex/single-flight уже существующего owner — подходящее место; library не
   содержит второго lock. Проверять key и freshness перед reuse. Не делать
   unbounded map по settings, revisions или queries.
3. **Optional body search:** `catalog::read_document` уже читает полный bounded
   SKILL.md для digest и возвращает parsed body; `discover` затем его отбрасывает.
   Будущий adapter может передавать bounded excerpts из этого же разрешённого
   чтения, **не открывать файлы заново ради этого прототипа**. Весь документ по-
   прежнему нужен для existing SHA-256. Если adapter сохраняет только prefix,
   отметить `complete=false` и применить свой aggregate retention budget ещё до
   накопления prefixes. Body bytes должны соответствовать тому же digest.
4. **Search:** owner получает invocation settings и повторяет текущие source/read
   проверки, затем строит `CurrentSkill` только из допущенных entries текущего
   снимка. После ошибки этих проверок не отдавать старые ranking results. Новый
   `portable_skill_search` возможен как future `tool/v6` export/handler, но здесь
   нет SDK wiring, descriptors, serde schema или нового автоматического routing.
5. **Load:** resolve hit ID через тот же catalog snapshot в existing
   `id + sha256 + catalog_path`; не конструировать path из query/source label.
   Сам `load_skill` остаётся свежим и независимо проверенным. Не использовать
   body excerpt как успешную загрузку полной инструкции.

Provider и tool в существующем sample — разные процессы, их `Arc` не общая
память. Если поиск реализовать в tool export, он должен владеть собственным
snapshot/index или получить явно спроектированную доверенную передачу; прямой
доступ к памяти provider не подразумевается. Ошибка search не должна незаметно
вызывать чужой process/export или расширять read permissions.

## Бюджеты и реальная граница памяти

| Ресурс | Default | Hard ceiling |
|---|---:|---:|
| Skills/current candidates | 128 | 128 |
| Sum borrowed input text lengths | 2 MiB | 2 MiB |
| Sum metadata bytes | 512 KiB | 512 KiB |
| Один supplied body (даже если индексируется prefix) | 128 KiB | 128 KiB |
| Bodies, получающие prefix index | 64 | 128 |
| Body prefix per skill / total | 16 KiB / 256 KiB | те же |
| Unique retained terms total | 16,384 | 32,768 |
| Retained term text bytes total | 256 KiB | 512 KiB |
| Terms per skill | 1,024 | 2,048 |
| Один normalized token | 64 bytes | 64 bytes |
| Query / distinct terms / results | 1 KiB / 32 / 32 | те же |

Body budgets можно выставить в ноль. Metadata полностью рассматривается до
body indexing; body budgets расходуются по отсортированным ID, а не input order.
Следовательно, перестановка входных records не меняет ни coverage, ни rank.
При маленьком aggregate budget лексикографически ранние источники могут получить
больше body coverage — сознательный простой baseline, не fairness scheduler.

Лимиты измеряют UTF-8 bytes и число objects, **не точный allocator RSS**. Один
индекс удерживает не более `max_term_bytes` term text, до 128 × (128+128+64) =
40 KiB identity/name text, 128 digests и ограниченное число descriptors/terms.
Структурные накладные расходы `Box`, `Vec`, `BTreeMap` и allocator зависят от
платформы. Во время build ограниченные maps и final vectors временно сосуществуют;
старый host-owned index также может оставаться живым. Это не OS memory quota.
`statistics()` возвращает логические счётчики, а не выдуманный peak RSS.

Входные строки уже принадлежат caller: библиотека не может предотвратить их
предыдущую allocation/чтение. Adapter обязан применять importer/transport caps
**до** deserialization/накопления. Нельзя повысить лимиты importer на основании
этого индекса. Для process-wide bound owner должен ограничить in-flight builds,
число retained `Arc` snapshots и concurrency запросов. Query scratch/результат
имеют bounded object count; результаты ссылаются на index, не клонируют bodies.

Время build ограничено preflight metadata и обработкой <=256 KiB body prefixes;
search рассматривает <=128 candidates ×32 query terms с binary search по <=2048
terms каждого. Нет hash-based nondeterminism и нет частотного rank boost. Hard
cancellation/timeout отсутствует: host может проверять cancellation до/после
этой синхронной bounded операции. Ни latency, ни ускорение не измерены.

## Coverage и отрицательный результат

`SearchCoverage` сообщает только данные текущего eligible subset:
metadata_partial, body_indexed, metadata_only, body_partial,
body_budget_skipped, matched и returned counts. `matched > returned` означает
ограничение выдачи, не потерю кандидатов при ранжировании. Per-hit coverage
различает supplied/indexed body и число рассмотренных prefix bytes.

**Ноль hits не доказывает отсутствие подходящего skill.** Возможны metadata-only
документы, сокращённые bodies, длинные пропущенные слова и языковые ограничения
лексического поиска. Даже полное lexical coverage не является semantic recall.
Не показывайте глобальные `statistics()` для исключённых sources пользователю;
search coverage специально не раскрывает их counts.

## Происхождение и проверка

Это оригинальная реализация идеи bounded lexical retrieval, не перенос исходника
OpenClaw/Hermes. Основание — локальный отчёт `reports/hermes-openclaw.md` из пакета
`proteus-agent-research-20261028`, включая pinned upstream references. Legacy
importer SDK pin `3f36a003` и исследованный Core pin `125a9eb` этим crate не меняются;
совместимость их runtime contracts не заявлена. Критерии проверки перечислены в
[VALIDATION.md](VALIDATION.md); выполнен только ручной source review.
