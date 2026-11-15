# Согласованные alpha API proposals: typed workflow и contracts runtime

**Два отдельных source proposals, не drop-in integration и не готовая upstream-интеграция.**
Здесь нет нового Core commit, обновлённых consumer pins или lockfiles. Порядок
интеграции обязателен: **реальный проверенный Core commit → согласованные pins
потребителей и штатная регенерация lockfiles → исполняемые gates**. Публикация
patches в delivery-репозитории этот порядок не заменяет.

| Proposal | Единственный изменяемый механизм | Потребитель после Core integration |
|---|---|---|
| [Typed WorkflowModule](typed-workflow/README.md) | Существующий Rust trait принимает и возвращает canonical typed DTO вместо промежуточного JSON text | Modules: все пять Core dependencies вместе |
| [Contracts runtime feature](contracts-runtime/README.md) | Один default-enabled feature отделяет schema-backed runtime APIs от canonical DTO surface | Desktop: root и client-common вместе |

Предложения независимы по назначению. Ни одно не добавляет второй runtime,
дублированные DTO, compatibility reader, alias API или обход общей authority.
Typed workflow не требует runtime feature: его process DTOs и trait остаются
доступны в обоих feature modes. Если принимаются оба предложения, consumer pins
должны указывать на реальный Core commit, включающий оба, а не на выдуманный SHA.

## Что доставлено

- Три **точных финальных patches** с исходниками regression tests и изменениями
  существующих canonical guides; альтернативных вариантов patches здесь нет.
- [Pinned dependency boundary](DEPENDENCIES.json): реальные текущие revisions,
  manifest identities, affected entries и неисполненные интеграционные prerequisites.
- [Composition](COMPOSITION.json): точные patch identities и область статической
  проверки; source application не означает compilation или runtime conformance.
- [SHA256SUMS](SHA256SUMS): контрольные суммы всех доставленных файлов, кроме
  самого checksum manifest. В каждом proposal есть собственные sources и checksums.

Core base: `befd30516aefa6f0a0ad5db9924ad4957160b8dc`; Modules base:
`200d1ec54f1217f61a31823db939df3799c638dc`; Desktop inventory base:
`a28cc7f507424a570e86dc44230ee323156fdf6c`. Patches применяются в соответствующем
upstream checkout, не в delivery-репозитории. На новых revisions нужен новый
source review и validation; чистое применение patch само по себе недостаточно.

Свежие upstream additions в canonical guides сохранены; Rust/tests/manifests
совпадают с ранее reviewed proposals. Старые delivery series повторно не применять; уже портированные capture/retry сохранены.
Реальные consumer pins по-прежнему отличаются от свежего Core base; см. dependencies.

## Ограничение доказательств

Выполнены source/hash/diff/application проверки; прямое форматирование исходников
не является type-check. **Успешных результатов compilation, tests, builds,
runtime, CI или benchmarks для этих proposals не заявлено.** Нет измеренных latency/CPU/RAM/build-time
выигрышей. Неизменённые wire versions не означают неизменённый Rust API: deliberate
normalization/error changes typed helper описаны в его README.

Этот packet следует рассматривать отдельно от существующих drop-in patch sets.
Публикация этого packet не обновляет upstream и не означает, что upstream-интеграция готова к слиянию.
