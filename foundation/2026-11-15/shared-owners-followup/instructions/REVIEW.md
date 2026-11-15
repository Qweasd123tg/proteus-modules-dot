# Независимый review: shared canonical instruction prefix

## Вердикт

**Source-level ACCEPT; production qualification остаётся открытой.** В точном
patch не найдено blocking semantic или source-level compile-interface issues.
Это условное принятие reviewed предложения, не подтверждение компиляции,
native tests или provider acceptance. Публикация этим review не выполнялась.

Reviewed patch SHA-256:
`3f76896c110cf15312547fd421e60bf1a5dcb0cbe6e7bb956e61797b849f9222`.
Независимый reviewer: runtime track, не автор candidate.

## Источники и повторённые проверки

Через GitHub заново прочитаны Modules main и untruncated tree. Main на момент
review: `42ae75355256190d01b569c85633b333d573f052`, 671 entries. Собственным
read/hash/apply checker, без исполнения авторского verification script,
повторены:

- 77 local source Git blob/SHA-256 identities против fresh remote tree;
- полный inventory 61 model-pack Rust-файла, без пропущенных Rust paths;
- два contract/re-export source blobs против remote Core tree на точном
  dependency pin `185225a7103088c444788374ca425d230060f55a`;
- одинаковость двух исходных canonical prefix bodies, их точное extraction
  в helper и неизменность остальных provider source bytes;
- неизменность старых test sources после вычитания одного нового метода;
- strict whitespace apply-check, zero-fuzz/no-offset apply, exact after,
  reverse и exact baseline;
- два порядка candidate + трёх Modules patches #165, девять disjoint targets,
  одинаковые результаты и точный reverse.

Пакет materialized sources не является полным build checkout. Remote
`model/model-pack/Cargo.toml` дополнительно прочитан: package называется
`model-pack`, поэтому предложенный affected runner target соответствует
manifest. Локальный runner только прочитан, не исполнен.

## Семантика

Общий helper получает только canonical `&[InstructionBlock]`. На exact Core
pin это прежние `String` text и `u8` priority. Оба прежних алгоритма выполняли
те же borrowed collect, `sort_by_key(Reverse(priority))`, blank filtering,
collect и `join("\n\n")`. Stable sort сохраняет исходный порядок при равных
ключах; это гарантия [Rust slice API](https://doc.rust-lang.org/std/primitive.slice.html#method.sort_by_key),
а не вывод из названия метода. Тип ключа и сам вызов не меняются. `kind` не
начинает влиять на порядок. Nonblank text не trim-ится и вход не мутируется.

OpenAI по-прежнему использует только canonical prefix для поля
`instructions`; empty prefix означает отсутствие поля. Legacy System
messages остаются в existing input shaping. Routing key, retention и
prompt-cache enablement не переносятся в helper.

Anthropic отдельно собирает **все Text parts** legacy System messages в их
порядке. Они соединяются до проверки `is_empty`, а не проходят canonical
`trim().is_empty()`. Поэтому whitespace-only legacy остаётся текстом; даже
сочетание нескольких empty legacy Text parts может оставить разделитель.
Patch не нормализует этот необычный, но существующий случай. System messages
по-прежнему исключаются из обычного messages payload.

Cache shaping не изменялся: при system breakpoint остаётся array с text и
cache-control; без breakpoint system остаётся строкой. Отдельные last-tool
breakpoint и top-level context fallback остаются на прежних ветках. Body
field insertion order не менялся. Helper не объединяет provider serializers.

## Тесты и пределы

Новый Anthropic test корректно создаёт enabled provider cache с TTL `1h` и
меняет только request `cache_instructions`; `cache_context=false`. Шесть
explicit triples × два режима действительно дают **один метод и 12
итераций**, не 12 tests. Expected strings сохраняют пробелы. Проверяются
отсутствие/наличие `system`, string/array, отсутствие top-level cache-control,
удаление System message из messages и немутирующая сериализация request.
Импорты и builder APIs доступны в inspected exact source scopes.

Этот тест не является полной cache-policy matrix: tools/context fallback,
disabled provider cache и multi-part legacy cases им не покрываются. Это
не blocker extraction: production paths не изменены, existing cache tests
сохранены. Оба прежних provider tests сохраняют equal-priority order,
nonblank bytes, blank omission и source immutability. Дедупликация их в один
generic test потеряла бы разные wire boundaries, поэтому они правильно
оставлены отдельно.

**Rust, Cargo, rustfmt, native tests, provider/runtime, CI и benchmarks НЕ
ЗАПУСКАЛИСЬ.** Toolchain отсутствует в PATH. Новый тест должен пройти на
baseline с tests-only overlay и на candidate. Нет необходимости требовать
fail-before для behavior-preserving extraction. Объявленные +2 production
LOC и отсутствие измеренного speed/RAM improvement описаны честно.

Требуется affected `model-pack --lib` и formatter на полном checkout перед
adoption. Text composition с #165 не является compiled integration.
