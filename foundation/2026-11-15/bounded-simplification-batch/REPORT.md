# Proteus: единый пакет ограниченных упрощений

Результат шести исследовательских направлений: **семь reviewed source-only
кандидатов в 11 файлах**, отдельное изменение поведения на HOLD и план
дедупликации CI без удаления тестов. Это не семь новых bugs и не production
integration. **Rust/Cargo/rustfmt, проектные tests, native UI, HTTP/provider,
replay, benchmarks и CI в этом проходе НЕ ЗАПУСКАЛИСЬ.**

Общий принцип: использовать существующего владельца данных/результата,
убирать недостижимую обвязку и проверять нужную generation до материализации.
Новый общий framework, cache или система запуска тестов не создаются.

Пакет продолжает принцип bounded themes из [integration plan](https://github.com/Qweasd123tg/proteus-modules-dot/blob/97d853bba033b02f996625967e0087b00d606c76/docs/integration-plan-2026-11-15.md): сначала конкретный owner/граница, затем qualification на фактических pins. Он не пересобирает весь прежний стек PR86–164 и не разрешает apply-all.

## Точные базы и свежесть

| Репозиторий | Проверенный ref |
| --- | --- |
| Core | `a3b82a676aa66a7a6b392dc45a29560590fd9b61` |
| Modules | `42ae75355256190d01b569c85633b333d573f052` |
| Desktop | `816cdc0b5017d0881ec0baea1edf017ce61cce93` |
| Delivery, база публикации и CI-анализа | `97d853bba033b02f996625967e0087b00d606c76`, до #164 включительно |

Upstream изменился во время исследования. Старые отчёты не перенесены на
новые SHA автоматически. Core targets/callers и parser targets повторно
сверены с fresh tree; их нужные preimages совпали. В Desktop уже присутствует
live-runtime inventory из прежнего предложения #148: здесь используются
fresh patches, повторно накладывать #148 на эту базу не нужно.

Для модели первоначальные 57 Rust-файлов больше не составляли полный пакет:
fresh model-pack содержит **61**, включая четыре новых Anthropic-файла.
Все 61 materialized source blobs сверены с fresh tree, поиск caller повторён
по этому набору. Восемь прежних файлов изменились. Terminal patch заново
сформирован на fresh preimage: его удаляемый код тот же; исходный patch
применялся с offset −21 и без fuzz. Новый patch имеет точный fresh context.

Fresh Cargo manifests Modules и Desktop теперь используют Core dependency
pin `185225a7103088c444788374ca425d230060f55a`, а не старый `41bdfffa…`.
Пакет не меняет эти pins. Совпадение source preimages и text application
не доказывает компиляцию с новыми dependencies. Полнота hash-инвентаря не
означает полный ручной аудит каждого файла.

## 1. HistoryCapture: один owned execution call

`patches/core-binding-owned-call.patch`, один файл, +18/−18.
Private tuple содержал и `ToolCall`, и binding с собственной копией того же
`execution_call`. Constructor создаёт первый только клонированием второго;
дальше отдельно меняется лишь recorded-флаг. Остаётся binding и флаг, а
сравнение читает вложенный execution call.

Сохраняются полная identity, raw arguments, порядок, partial ACK, reserved
identities, ошибки, snapshot-local индексы и различие model/execution call.
Убирается один deep ToolCall clone на binding при construction и clone
capture. Private derived Debug tuple меняет форму. Public DTO/wire не меняются.
Это не измеренное уменьшение RAM/CPU.

**Checkpoint revision здесь не меняется.** Старый двухфайловый combined patch
отозван и не включён. Отдельный NaN-путь описан ниже, не подразумевается этим
ownership cleanup.

## 2. History cache: сначала допуск generation, затем payload

`patches/core-history-cache-admission.patch`, два файла, +20/−6.
Reader уже хранит cached source и source, наблюдавшийся при открытии. Если
они различны, финальная freshness-конъюнкция всё равно ложна. Current-only
conversation/model readers теперь отказывают до decoding полного payload.
Неверная named revision также отсеивается до чтения transcript rows.

Final source reread в `finish` сохраняется, поэтому append во время decoding
не становится свежим результатом. Matching named stale revision и explicit
stale display сохраняются; обычный `view` не переведён на early rejection.
Checks accepted data, canonical fallback и отказ relabel новой истории под
потерянную revision не удалены. `SessionReadModel::matches` оставлен: позднее
наблюдение workspace не тождественно раннему сравнению.

Обоснование `load` зависит от проверенного current-only caller, принимающего
лишь fresh=true. Будущий stale consumer не должен предполагать старые return
cases. Fresh path получает ещё одно сравнение fingerprint, потенциально по
blob inventory. Initial scan остаётся. Не обещается constant-time predicate
или универсальное ускорение. Existing tests прочитаны, но не исполнены;
не вся новая early-return matrix автоматически покрывается старыми cases.

## 3. Patch parser: передача результата вместо двух snapshot clones

`patches/modules-patch-parser-ownership.patch`, два production-файла и один
существующий test file, +48/−51; production +9/−14.
Проверенный one-shot caller игнорировал первый cloned preview, затем получал
ещё один cloned result. Preview теперь заимствует slice, consuming `finish`
возвращает owned `ApplyPatchArgs` вместе с environment_id.

Грамматические переходы, `process_line`, validation/error propagation и
filesystem operations не меняются. Но private API capabilities уже:
невозможно хранить независимый preview и продолжать mutable parser; после
ошибки consuming finish нельзя дописать данные и повторить finish на том же
instance. Проверенные callers этим не пользуются. Это эквивалентность
проверенного one-shot пути, не всех теоретических прежних streaming callers.

Сохранены 11 test methods и 39 assertion macros, но это **не доказательство
тождественного покрытия**: large character-split test теперь проверяет итог
finish вместо последнего preview. Остальные preview-контроли остаются.
Новых suites нет. Move сохраняет buffers/spare capacity, поэтому удаление
двух clone sites не означает гарантированно меньшую retained RAM. Production
подаёт patch один раз; quadratic production streaming cost не заявляется.

## 4. Native models: удалить мёртвый reader и ложную матрицу теста

- `patches/modules-single-terminal-reader.patch`: −18 production lines.
  Единственный caller `translate_non_message_event` находится в wildcard
  stateful dispatch. `response.completed` раньше него уходит в
  `finalize_completed_event`. Удаляется недостижимый fallback reader, не
  реально выполнявшийся второй parse. Активный finalizer, stateful IDs,
  terminal failures и nonstream path сохраняются. Runtime speedup не следует.
- `patches/modules-openai-fallback-test-scope.patch`: −10 test lines.
  `for anthropic in [false]` никогда не проверял положительный Anthropic
  fallback. Убираются две мёртвые ветки и box; имя сообщает фактический OpenAI
  scope. Request/body/terminal assertions остаются; отдельный negative
  Anthropic test побайтно прежний. Два Tokio tests остаются двумя, удалено
  **ноль исполняемых test cases**. Внешние exact-name filters потребуют
  учитывать переименование.

Source review повторён на свежих 61 файлах. Старые #108/#158/PR57–58 не
считаются новой работой; вывод не переносит их историческое evidence на
свежий runtime. Serializer tests разных providers не объединялись: они
проверяют разные JSON contracts.

## 5. Desktop: два небольших owner cleanup

- `patches/desktop-shared-surface-adapter.patch`: +8/−18 в одном файле.
  Три одинаковых native focus/rehost adapters используют один private helper.
  Runtime selection, Settings/Preview isolation и embedded flag остаются у
  callers. Strong Entity сохраняется в view; callback по-прежнему weak.
  Новых runtime/cache ownership и цикла ссылок не появляется.
- `patches/desktop-singular-reply.patch`: +14/−16 в двух файлах.
  Всегда singleton `Vec<Part>` превращается в `Part`, единственный caller
  использует `.child`. Renderer/language guards, content updates, subscriptions,
  cache retain, rehost, plain row ID и UI styling сохраняются.

Это не ремонт lifecycle bugs, не объединение разных SurfaceView типов и не
измеренный frame-time/RSS выигрыш. Оба fresh patches повторно проверены на
`816cdc0`; native compilation/focus/repeated-open-close/rehost smoke не был
выполнен. Существующие несвязанные UI tests не выдаются за покрытие этих cuts.

## 6. Дедупликация tests/CI: план, а не удаление защиты

[Отдельный статический план](TEST-DEDUP-PLAN.md) показывает четыре копии
envelope, одинаковые без локальной DEADLINES policy, и две identical skills
probe/verifier copies. Это 105+15 повторных **определений** методов, не такое
же число доказанно ненужных запусков. Сейчас safe unconditional deletions: **0**.

Нужен один существующий implementation owner, тонкие policy entrypoints и
сохранённые wiring checks, не новый supervisor framework. CI input hashing,
isolated imports, exact test-name/count gates, workflow paths и dependency
closure должны обновляться вместе. Historical PUBLICATION/snapshots не надо
переписывать под новый код. Skills lanes используют разные Core pins;
одинаковые script bytes не разрешают удалить один compatibility lane.

Publisher независимо повторил 20 source-blob hashes и static AST/string
equality checks. Репозиторные controllers/tests не импортировались и не
исполнялись. Это не CI run и не измерение его ускорения. План не входит в
очередь применения patches.

## Отдельный HOLD: insertion-driven revision и NaN

[HOLD report](hold/BOOL-REVISION-HOLD.md) и
[отдельный patch](hold/02-insertion-driven-revision-HOLD.patch) сохранены только
как явно отделённое предложение изменения поведения. В recommended seven
и composition checks оно не включено.

History использует derived PartialEq, а native context/hosted scores могут
иметь NaN. История с NaN может быть не равна собственной копии даже при
unbound no-op. Старое clone/equality тогда повышает revision, insertion bool
нет. Поэтому безусловная эквивалентность отозвана. Это source/type-level
контрпример, **не выполненный Rust reproducer** и не утверждение, что штатный
JSON provider доставляет NaN.

HOLD требует явного решения о revision semantics и native in-memory проверки
NaN/no-op, normal no-op, bound insertion, batch и late-error outcome. JSON-only
fixture или Python-модель этого не заменяют. Late batch error по-прежнему
может следовать после ранних вставок до revision increment; атомарность этим
patch не исправляется. Publishing HOLD не означает разрешение применять его.

## Что проверил publisher

1. Свежие refs, exact Git blobs и SHA-256; changed/new model files действительно
   прочитаны на fresh revision, а не потеряны при переносе старой выборки.
2. Для каждого из семи active patches: strict `git apply --check
   --whitespace=error-all`, GNU `patch --fuzz=0`, reverse и точное восстановление
   исходных target bytes. Все имеют exact fresh context без offsets.
3. Два порядка на каждый репозиторий: Core 2 patches, Modules 3, Desktop 2.
   В каждой паре порядков итоговые 11 target files побайтно совпадают; все
   выбранные patches имеют непересекающиеся target sets. Это text composition,
   не cross-repository integration и не whole-tree/runtime equivalence.
4. Независимые source reviews, включая свежие model/Desktop checks и split
   runtime hashes. Parser API/test-oracle/memory caveats сохранены.
5. Public allowlist и проверка относительных ссылок; ручной и pattern scan
   не нашли локальных путей, credentials или личных данных. Полные source
   snapshots и raw execution logs не включены. Это не универсальная гарантия
   обнаружения любых secrets.

Python использовался только для AST/hash/diff/file bookkeeping, а Git/GNU
patch для текстовой применимости. Здесь **ноль выполненных Rust tests**.
Прошлые synthetic passes PR164 или runtime результаты прежних аудитов не
складываются с этой работой. Отсутствие GitHub checks не считается CI PASS.

Перед production adoption нужны штатные affected targets на выбранных
полных checkout и pins: Core session_store/history_capture/checkpoint
boundaries, Modules codex-patch/model-pack, Desktop affected native paths.
Измерения должны отдельно сравнить fresh/stale history и реальные allocations,
если нужен количественный вывод. Не добавлять дублирующий framework ради
подсчёта большего числа tests. Upstream, pins, CI workflow и пользовательская
установка этим delivery-пакетом не меняются.
