# Проверенные исходные дополнения к фундаменту

Шесть неизменённых после review патчей поверх 25 исходных патчей из уже
объединённых [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60) и
[PR61](https://github.com/Qweasd123tg/proteus-modules-dot/pull/61).
Delivery baseline — `73d438d49be6ef15307abb179d1beaa6cbeb7312`, tree
`14339a1b851f5a31bb4ff21aac1f00de685902d5`.
**`success-evidence: false`**: source review и статическая композиция не
подтверждают успешную компиляцию, тесты, runtime, CI или измеренный выигрыш.

## Что меняется

| Патч | Изменение и сохранённая граница |
|---|---|
| `core/01-derived-only-streaming-reads.patch` | Пять derived-only путей journal больше не удерживают отдельный `Vec<JournalRecord>` и не строят неиспользуемые результаты полной projection. Все records/blob проходят прежний scanner и authoritative validator; поздняя storage error сохраняет приоритет над ранней semantic error. Это не incremental recovery и не общий предел памяти validator. |
| `core/02-cancel-before-peer-lease.patch` | Уже видимая отмена получает приоритет перед готовым role permit: не арендуется fresh/resume peer, используется существующий rollback. Отмена после выбора permit и lifetime worktree не меняются. |
| `modules/01-catalog-deadline.patch` | Ожидание coalescing lock входит в существующий 30-секундный timeout каталога. Cache/TTL, OAuth и single refresh сохраняются; timeout остаётся кооперативным. |
| `modules/02-retry-request-template.patch` | Cloneable OpenAI request делит одно JSON encoding внутри retry phase. OAuth refresh создаёт новую phase; non-cloneable stream сохраняет прежний factory path. Encoded bytes живут и во время backoff: меньший RSS не обещается. |
| `modules/03-reader-terminal-reasons.patch` | Readers различают EOF, read error и drain expiry. Остановка readers и exit команды больше не подразумевают полноту потока; сама правка не включает capture. |
| `modules/04-opt-in-exec-source-capture.patch` | В существующем `shell_tools` явно включаемый raw-prefix capture до preview truncation и `read_exec_capture` через прежний tool RPC. Нет второго shell, нового slot, standalone capture-библиотеки, dependency или Cargo pin. |

Source capture по умолчанию выключен. Оператор выбирает directory и limits;
вывод может содержать secrets, а запрошенные ranges доступны configured
host/model pipeline через обычный RPC. Anonymous files/handles относятся к
одной generation, не являются durable artifacts. Quota действует на binding,
не на весь process/RSS; TTL — logical expiry с lazy cleanup, не deletion SLA.
Queue/file failure после spawn не повторяет команду и не подменяет её exit
code. Sealed prefix, range EOF и complete stream — отдельные состояния.

## Порядок и зависимости

Патчи применяются к соответствующим upstream checkout, **не** к delivery repo:

- Core: `925de0fc5ee5995409b11e42b216a15ca12f76d0`;
- Modules: `8ec681b861d290d1bcf0d9d9b3087bb463dfd9b2`;
- реальная Core dependency Modules остаётся
  `1f533a13f20a93bf164f7c8a169553b0b219bb51`, без фиктивного нового pin.

Воспроизводимая полная цепочка — `COMPOSITION.json`, steps 1–25 (merged
baseline), затем 26–31 (эти шесть патчей). Порядок внутри каждого repository
сохраняется. Перед каждым применением выполнена обычная проверка
`git apply --check --whitespace=error-all`; ослабление context/whitespace,
zero-context, forced/three-way/reject application не использовались.

Для отдельного применения `core/01` необходима прежняя journal-цепочка:
PR60 borrowed transcript parts → PR61 reset frontier → reset-scoped timestamps
→ consuming read-model renderer. Для `modules/04` обязателен `modules/03`.
Остальные четыре новых патча применяются непосредственно к своему pinned
upstream. Точные пути, SHA-256 и URLs — в `DEPENDENCIES.json` и `SOURCES.json`.
Патч retry имеет SHA-256 `e80b2e9d08c93eec65cb760977a0d5f1a07f0a0a9c6eb3a7b2582afde2745a57`.

## Проверка и документы

- Все 25 baseline patch blobs сверены с указанным merged Git tree.
- 96 original files сверены с pinned upstream blobs; вся цепочка из 31 патча
  применена и обращена до точного восстановления исходных bytes.
- Каждый новый патч отдельно с его prerequisites воспроизводит frozen
  candidate byte-for-byte. Полная композиция содержит 127 файлов выбранного
  среза; это не полный checkout или full-workspace gate.
- Пересекающийся `docs/reference.md` сохраняет baseline и обе новые темы;
  frozen patches не переписывались. Source behavior и правила остаются у
  существующих owners: Core `docs/architecture/subagents.md`, Modules
  `docs/reference.md` и `model/model-pack/UPSTREAM.md`. Этот README — инструкция
  доставки, не новый нормативный guide или параллельная конфигурация.

`SOURCES.json` содержит исходные identities и отдельные preimage/candidate
hashes; `COMPOSITION.json` — порядок, pre/post hashes и восстановление;
`VALIDATION.json` — статические результаты и границы; `SHA256SUMS` — весь пакет
кроме самого checksum-файла. Regression sources присутствуют, но успешного
executable evidence для этих изменений нет. Нет измеренных CPU/RAM/latency
цифр. Публикация исходников не означает deployment, готовую portable-сборку
или выполненную проверку продукта.

Для исполняемой проверки нужны существующие scoped gates: Core journal /
session-store / read-model и process-agent admission/reuse; Modules model-pack,
shell-tool и affected independent/aggregate process fixtures. Для затронутых
wiring/contracts — применимый full/module-swap gate из действующих
[Core testing rules](https://github.com/Proteus-harness/Proteus-core/blob/925de0fc5ee5995409b11e42b216a15ca12f76d0/docs/development/testing.md)
и [Modules rules](https://github.com/Proteus-harness/Proteus-modules/blob/8ec681b861d290d1bcf0d9d9b3087bb463dfd9b2/AGENTS.md).
