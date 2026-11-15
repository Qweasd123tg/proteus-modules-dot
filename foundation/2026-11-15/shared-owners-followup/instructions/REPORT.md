# Modules: один владелец canonical instruction prefix

## Решение и статус

Ограниченный source-кандидат: одинаковые восемь строк сортировки и сборки
canonical instructions в OpenAI и Anthropic получают одного владельца,
`adapters/context_render::instruction_text(&[InstructionBlock])`.
Этот existing private модуль уже отвечает за model-facing formatting;
новый crate, framework, DTO, cache или межмодульная зависимость не нужны.

**Польза здесь в единственном месте изменения правила, не в ускорении.**
Две реализации алгоритма становятся одной; provider-specific wrappers
сохраняются. Production diff +21/−19 строк: это **+2 LOC**, а не сокращение
общего размера. Число сортировок на один request не уменьшается, те же
temporary vectors и String остаются. CPU/RAM/RSS не измерялись.

Независимый review runtime-track дал **source-level ACCEPT** для exact patch;
он отдельно перепроверил sources, extraction, apply/reverse и композицию.
Это не compilation approval. Rust/Cargo/rustfmt отсутствуют; compilation,
Rust tests, provider HTTP, runtime, CI и benchmarks **НЕ ЗАПУСКАЛИСЬ**.
Это не production-ready patch и не новое исправление функционального дефекта.

## Точные источники и предыдущая работа

- [Modules main](https://github.com/Proteus-harness/Proteus-modules/tree/42ae75355256190d01b569c85633b333d573f052)
  повторно проверен через GitHub ref; он совпадает с базой #165.
- Публичный Core dependency pin остаётся
  `185225a7103088c444788374ca425d230060f55a`. На этом exact pin прочитаны
  `canonical_request.rs` и re-export `model_standard/mod.rs`: instructions
  имеют тип `Vec<InstructionBlock>`, priority — `u8`, text — `String`.
- Fresh untruncated Modules tree: 671 entries. Все 61 Rust source-файл
  model-pack materialized и проверены по Git blob SHA; всего 77 source
  identities, включая runtime wrappers, документацию, runner и targets #165.
  Полнота inventory не означает ручной аудит всех 61 файлов.
- [#165](https://github.com/Qweasd123tg/proteus-modules-dot/pull/165) уже
  публикует parser ownership, dead terminal reader и truthful fallback-test
  scope. Они не представлены здесь как новая работа. В прежнем model report
  одинаковый instruction prefix был отмечен как допустимый future cut, но
  сознательно не включён. Здесь доведено именно это отложенное предложение.
- [#57](https://github.com/Qweasd123tg/proteus-modules-dot/pull/57) убирал
  copies instruction blocks перед sort, а не создавал общий renderer.
  Borrowed сортировка уже есть в текущем upstream и остаётся прежней.
  PR search по instructions/render и чтение #165 не выявили уже доставленного
  equivalent shared-prefix patch; это bounded search, не доказательство
  отсутствия любого похожего исторического текста.

## Почему извлечение сохраняет поведение

Оба исходных префикса побайтно одинаковы. Проверка сравнивает helper expression
с ними после только двух явных преобразований: `request.instructions`
становится slice argument `instructions`, а `let text = expression;`
становится возвращаемым expression. В обоих callers expression заменён
вызовом helper. Остальные provider source bytes, кроме нужного import,
побайтно прежние. Это source-level доказательство извлечения, **не запуск Rust**.

1. Borrowed `Vec<&InstructionBlock>` по-прежнему собирается в request order.
   Никакой мутации входного `Vec` или deep clone blocks не добавлено.
2. Тот же stable `sort_by_key(Reverse(priority))` сохраняет убывание priority
   и исходный порядок при равных priority. Instruction kind как прежде не
   фильтруется и не задаёт отдельного порядка.
3. Тот же Rust `trim().is_empty()` отсеивает только полностью blank blocks;
   непустой текст не обрезается. Unicode whitespace, leading/trailing bytes
   и разделитель `\n\n` используют тот же code path.
4. OpenAI wrapper по-прежнему возвращает `None` для пустого prefix. Legacy
   System messages не перемещаются в `instructions`: их existing input
   handling остаётся provider-specific.
5. Anthropic wrapper отдельно собирает только Text parts из System messages
   в исходном порядке. **Важное различие:** legacy whitespace text не проходит
   canonical blank filtering. Его combining/nonempty rules оставлены ровно
   прежними. Helper не получает messages и не может случайно нормализовать их.
6. Anthropic cache-control/string-versus-array shaping и removal of System
   messages из обычного messages payload вообще не менялись. OpenAI cache
   routing, other fields, key ordering и serialization тоже не менялись.
7. Scope helper — existing private adapters subtree. Public contracts, process
   protocol, capabilities, registration, pins и authority не меняются.

Не объединяются provider serializers, error enums, retries, stream states или
cache policies. Внешне сходные branches принадлежат разным contracts; общий
«универсальный model adapter» потребовал бы режимов и расширил бы риск.

## Native тесты: что сохранено и что добавлено

Все прежние test functions/assertions сохранены побайтно. В частности,
оба `request_preserves_instruction_order_and_file_content_without_mutating_source`
остаются: они проверяют tie order, priority, blank omission, сохранение bytes
и немутирующую сериализацию каждого provider. Они не удаляются ради дедупликации:
это разные wire boundaries.

В существующий Anthropic `request_tests.rs` добавлен **один** test method
`canonical_prefix_preserves_legacy_system_and_cache_semantics`:
6 explicit input/expected triples × 2 cache modes. Это 12 table iterations,
не 12 зарегистрированных tests. Cases отделяют empty/blank canonical от blank
legacy text, combined canonical+legacy и legacy-only. Проверяются system
string/array, cache TTL, отсутствие top-level cache-control, отсутствие
дублированного System message и unchanged source request.

Этот test добавлен как behavioral boundary guard, а не как source-layout
assertion. Он **не исполнен**, ни на baseline, ни на candidate. Source equality
или Python bookkeeping не заменяют его и не дают native PASS.

## Выполненные проверки

`VERIFICATION.json` фиксирует:

- 77 source Git blob identities против свежего exact tree;
- exact duplicate-prefix/extraction checks и сохранение остальных provider
  source bytes/существующих tests;
- `git apply --check --whitespace=error-all`, GNU `patch --fuzz=0` без offsets,
  candidate byte equality, reverse и точный возврат baseline;
- два порядка композиции с **всеми тремя Modules patches #165**: четыре
  patches имеют девять непересекающихся targets, результирующие source bytes
  совпадают, reverse возвращает baseline. Это text composition, не product
  integration или qualification новых dependencies;
- текущая доступность toolchain: `rustc`, `cargo`, `rustfmt` не найдены в PATH.

Patch SHA-256:
`3f76896c110cf15312547fd421e60bf1a5dcb0cbe6e7bb956e61797b849f9222`.

## Оставшиеся gates

На полном Modules checkout с тем же Core pin: rustfmt, then
`python3 scripts/test.py -p model-pack --lib`. Новый тест сначала выполнить
на baseline с tests-only overlay, затем на candidate: это behavior-preserving
refactor, поэтому ожидается PASS в обоих случаях, а не искусственный fail-before.
Штатный runner прочитан: он использует exact Cargo dependency harness и
`cargo test --locked`; он не запускался здесь. Если позже расширится shared
public boundary, потребуется full/modules wiring gate, но этот patch её не
меняет.

Нет причины запускать платный provider или менять installation ради private
formatting cleanup. Portable rebuild остаётся отдельным adoption шагом по
AGENTS.md при фактическом изменении приложения. Здесь upstream/установка не
менялись. Не добавлять CI framework ради маленького helper; объединить этот
candidate с bounded reviewed theme или оставить непубликуемым, если его
maintenance value недостаточна.
