# Portable: финальная совместимость Desktop и Extensions

2026-11-15 UTC. Исправление ранее известной **D2-02**, не новая независимая
находка. Это проверенный синтетическими Python-сценариями кандидат, а не
интеграция upstream, полноценная сборка или разрешение на выпуск.

## Проблема и граница исправления

[Предыдущий аудит](https://github.com/Qweasd123tg/proteus-modules-dot/blob/cfb960a852685d79a0d9a0059907bb9faab95aa3/research/proteus-continuous-audit-2026-11-13/evidence/round2-desktop/REPORT.md)
уже описал D2-02: `--components desktop extensions` и `--full` обходят обе
односторонние preflight-проверки. Финальный `read_record(stage)` проверяет
наличие assets и executable, но не сопоставляет protocol/required_features
расширений с возможностями Desktop. На текущем Desktop
`7eaf70c67dabba8595d98029c875ffc3f59209ad` этот путь сохранился.

Кандидат добавляет один `verify_packaged_extensions` и вызывает его после
`read_record(stage)`, перед `publish`. Проверяются фактически упакованные
`extension.json` против `desktop_protocol` и `desktop_features` итогового
`release-sources.json`, независимо от выбранных компонентов. Одного равенства
protocol недостаточно: required_features должны поддерживаться хостом.

Ранняя проверка базы остаётся структурной. Поэтому можно совместно обновить
Desktop и Extensions, исправляя старую несовместимость, или пересобрать
Desktop, восстанавливая отсутствующую metadata. Без такого ремонта core-only
и reuse теперь явно отклоняют отсутствие protocol/features. Это намеренное
изменение допуска, не полностью behavior-preserving refactor. Возможности
хоста не угадываются из требований самих расширений.

## Фактически выполненные проверки

Python **3.12.14**, `-I -B -S`, stdlib. Проверены точные source Git blobs и
SHA-256; production/test bytes не менялись при исполнении. Тестовые файлы и
фикстуры создавались отдельно; пользовательские установки и исходные
upstream checkout не изменялись. Независимое чтение выполнено до запуска и
после получения логов.

| Дерево | Фактический результат |
| --- | --- |
| Unpatched Desktop + четыре выбранных новых регрессии | 4 ожидаемых assertion failures: `SystemExit not raised`, без errors |
| Standalone candidate | 12 методов PASS |
| #142 + вариант кандидата для #142 | те же 12 методов PASS; 6 адаптированных методов serialization PASS |

Это **12 новых уникальных методов**, а не 30 новых проверок. В combined-дереве
проверено 18 методов; повторный standalone-прогон не добавляет уникального
покрытия. Четыре baseline failures показывают старое неверное поведение, не
являются passing tests.

Новые тесты исполняют настоящие `main`, `assemble`, preflight helpers,
`read_record`, финальный validator и `publish`. Компиляция, разрешение
исходников, создание provenance, упаковщики и доставка notices заменены
синтетическими производителями. Файлы с executable mode инертны и не
запускаются; неожиданные subprocess-вызовы в новом suite запрещены.

Проверены protocol mismatch и missing feature в joint/full, сохранение
прежнего destination и очистка stage при отказе, совместимая full-пара,
ремонт старой базы, восстановление metadata, unrepaired core/reuse, reuse
по shipped metadata вместо текущего checkout, финальные manifests после
успешного preflight и неизменность `--plan`. Отказы происходят до publish.

## Взаимодействие с #142: сериализация обновления

Оба порядка применения standalone patch и точного опубликованного #142
механически дают одинаковые пять изменённых файлов без fuzz. Однако старый
serialization test fixture намеренно заменяет `read_record` и содержит
неполный набор assets/metadata. Новый финальный gate нельзя считать
совместимым с этим fixture без адаптации.

Поэтому дан отдельный **альтернативный** `portable-compatibility-on-PR142.patch`.
Он применяется после #142 и включает те же production-изменения плюс три
явные правки старого test harness: stub нового gate только в упрощённом
serialization fixture и включение gate в проверку порядка вызовов/охвата
блокировкой. Новый suite использует настоящий gate и на combined-дереве.
Production validation не отключается.

Все шесть адаптированных serialization-методов прошли: в том числе lock
coverage до archive, сохранение двух обновлений, release lock после ошибки
и inode-проверка с отдельным stdlib Python-процессом. Один из этих методов
создаёт настоящий tar.gz из инертных fixture-файлов. Это не portable release
и не проверка настоящих builders. Standalone patch не исправляет потерю
параллельного обновления без #142.

## Взаимодействие с #161: active panes

Из точных опубликованных patches #161 применены только reference-hunks
`src/declarative/protocol.rs` и `packages/files/extension.json`, с проверкой
Git identities исходных файлов и patch blobs. Кандидатный Python validator
проверен на их реальных объявленных protocol/features:

- Files из #161 + metadata непатченного Desktop: ожидаемый отказ по
  `documents.active_panes.v1`.
- Тот же Files + metadata согласованного Desktop из #161: принят.
- У обоих Desktop protocol остаётся **4**, что подтверждает необходимость
  feature-проверки отдельно от protocol.

Это два результата проверки объявленных manifests, не два Rust tests и не
handshake. Весь #161 не собирался и не квалифицировался; его rollout HOLD
и непройденные native/wire gates сохраняются.

## Точная поставка и применение

База Desktop: `7eaf70c67dabba8595d98029c875ffc3f59209ad`.
Reference Extensions: `f82b3ad753cf397f8a931b193aa1943af1ef07a7`.
Delivery snapshot при начале работы: `cfb960a852685d79a0d9a0059907bb9faab95aa3`.
Эти upstream main refs повторно проверены перед подготовкой публикации.

Выберите **один** вариант:

1. На чистую базу Desktop: `portable-compatibility.patch`.
2. На эту базу после точного #142: `portable-compatibility-on-PR142.patch`.

Не применяйте оба варианта и не накладывайте второй поверх первого.
Оба прошли strict whitespace apply-check, zero-fuzz применение и обратное
восстановление соответствующей базы. Для #142-ветки это включает удаление
добавленного нового тестового файла при reverse. Исходные dependency pins
не изменяются. SOURCES.json и VERIFICATION.json фиксируют hashes и границы.

## Что не проверено

Не запускались Cargo/Rust/rustfmt, настоящие builders/package.py,
разрешение источников, release metadata producer, полная поставка,
нативное окно, wire/handshake, installed executables или live providers.
Rust toolchain в текущем окружении отсутствует. Полный проектный suite и
реальный portable build не выполнены. Нет performance/скоростного вывода.

Gate доверяет metadata и не доказывает совпадение её заявлений с реальными
байтами Desktop. Общая schema-validation malformed JSON/типов, гонки внешних
writers, аутентификация и security policy не входят в эту правку.
Не заявляется отсутствие других packaging-дефектов.

Публикуются только отчёт, review, provenance, компактная верификация и два
patch-варианта. Raw logs, локальные пути, полные source snapshots и fixtures
не включаются. Merge в delivery repository не применяет кандидат upstream
и не превращает отсутствие CI checks в CI PASS.
