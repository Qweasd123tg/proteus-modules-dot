# Согласованность runtime и работа после reset

Исторический source-only пакет для Core
`925de0fc5ee5995409b11e42b216a15ca12f76d0`, а не набор для повторного применения
к текущему upstream. Delivery PR60/61 слиты, их изменения перенесены владельцем.
Слияние delivery и перенос upstream не являются доказательством выполнения tests.

**Историческая поправка 08:** исходный artifact `37cc15d3…` был неполным:
отделив session mode от AppConfig, он пропустил наследование effective mode
через `/new-session` с явным `source_session_dir`. Исправленный 08 заменяет
его целиком и включает точную правку владельца из Core
[`b062bb34634bb7de346d898fb326a9e154c6ed69`](https://github.com/Proteus-harness/Proteus-core/commit/b062bb34634bb7de346d898fb326a9e154c6ed69):
отдельное чтение/применение runtime mode, addressing assertions и текст guide.
Это всё ещё patch для исходной базы `925de0f`; исправление уже есть в `b062bb3`
и сохранено в текущем Core
[`befd30516aefa6f0a0ad5db9924ad4957160b8dc`](https://github.com/Proteus-harness/Proteus-core/commit/befd30516aefa6f0a0ad5db9924ad4957160b8dc).
Повторно применять 08 к ним нельзя. Успешный запуск tests не заявлен.
Старый 08 с SHA-256 `37cc15d331fad55cf66bec5824fe1f6b9bdbed80aacf40da0769f40ccb209cca`
заменён полным `3f9a9ae5b8b58248b5e80fb362069ff5140e3372105ef19cc5bb7b879ba926c2`,
а не дополнен ещё одним runtime patch. Старый вариант остаётся только в Git history.

## Изменения

- `01-bound-reasoning-defaults.patch`: после публикации новой сборки повторное
  включение reasoning берёт effort/summary/budget из её registry. Удалена
  отдельная startup-owned копия defaults. Неудачный reload не меняет источник;
  уже принятые invocations сохраняют snapshot, unrelated reload не удаляет
  session override. Исправлены оба re-enable paths. Regression sources
  охватывают persistence failure и сборку без модели.
- `02-transcript-reset-frontier.patch`: renderer начинает с последнего
  не скрытого live-turn фильтром Replace без compaction, поскольку этот record
  сбрасывает transcript и все dedup sets. Сам Replace включён в replay.
  Full journal validation, root/committed-part/lifecycle facts, final results
  и первые даты всё ещё читаются глобально. Prefix-equivalence regressions
  сравнивают каждый валидный prefix с replay от нуля; отдельно закреплён
  запрет повторного ExchangeId через Replace. Это **не** incremental disk
  recovery и не cache, который доверяет одному history_revision.
- `03-outbound-exact-size.patch`: первый outbound проход по owned `Value`
  считает compact JSON length, не генерируя escape fragments строк и
  пунктуацию контейнеров через serializer. Числа форматируются самим serde_json.
  Полный обход остаётся, sole writer по-прежнему сериализует принятый frame.
  Atomic admission, frame-before-queue error priority, data/control budgets,
  Framing и receive accounting не меняются. Это **не** full encode-once и не
  доказанный CPU выигрыш, особенно для numeric-heavy кадров. Helper допустим
  только для `Value` и pinned default CompactFormatter, не generic Serialize;
  escape/number/error parity требует повторной проверки при изменении формата.

- `04-generation-local-optional-methods.patch`: optional model catalog/quota
  проверяются тем broker generation и exact export, которые принимают invocation.
  Отдельный manifest probe больше не может разрешить вызов после restart с
  другим feature acknowledgement. Только broker-owned typed UnsupportedFeature
  превращается в отсутствие metadata (`None`); worker error string, handshake,
  transport и lineage ошибки остаются ошибками. Нет union capabilities между
  exports и изменения wire/config. Lazy initialize теперь входит в обычный
  start deadline; отдельный handshake timeout сохраняется. Regression sources
  покрывают смену поколений, siblings/parent, cancellation и diagnostic context.
- `05-borrowed-newline-read.patch`: готовая первая JSONL строка разбирается из
  `BufRead::fill_buf` без прежнего временного Vec и копии. Owned JSON Value и
  его allocations остаются. Split/unterminated frames используют прежний
  accumulation path. UTF-8→from_str, consumption при ошибке, CR/LF/EOF и
  exact limit precedence сохранены; это не zero-copy JSON decoder.

- `06-reset-scoped-timestamps.patch`: после reset message/part date indexes
  заранее содержат только нужные suffix identities; заполнение первых дат
  всё ещё читает весь journal. Нет второго wanted set или второго date index;
  no-reset путь прежний, call dates остаются глобальными. Vacant slots явно
  отличаются от valid nonzero sequence. Это сокращение временных date keys,
  а не обещание общего RAM bound.
- `07-consuming-read-model-renderer.patch`: renderer получает records по
  владению. Usage/context готовятся до него, history переносится один раз;
  вся fallible summary logic (включая filesystem наблюдения) остаётся после
  renderer. Erased prefix payloads освобождаются до первой строки, затем
  освобождается payload каждого пройденного record. Буфер Vec с headers и
  исходный full-parse peak остаются; это не streaming recovery. Generic
  callbacks сохраняют FnOnce без новых Send/Sync/'static требований.
- `08-session-mode-profile-baseline.patch`: временный permission mode больше
  не переписывает опубликованный AppConfig. Несвязанное изменение профиля
  не сбрасывает session override; первый Config Builder save не записывает
  временный Plan как profile default. Runtime остаётся единственным владельцем
  effective mode, UI продолжает читать его. Явный source-session переносит
  effective mode отдельным override до `start_session`, в том числе при выборе
  другого workspace, не меняя default новой сессии; source-less путь остаётся
  прежним. Старые addressing tests уже требовали inherited Auto, новые assertions
  дополнительно закрепляют published Normal. Propagation между сессиями остаётся
  предусмотренным per-session eventual reload, не общей транзакцией.

## Применение только к исторической базе

Ниже — воспроизведение состава на `925de0f`, не инструкция установки на свежий
Core. Для текущего checkout сначала сравните уже портированные изменения;
само наличие patch в delivery не означает, что его нужно применять снова.

`SOURCES.json` фиксирует исходные Git blobs, candidate hashes и порядок
проверенной композиции. Патчи относятся к Core checkout, а не к delivery repo.
Сначала проверяйте `git apply --check --whitespace=error-all`, затем применяйте
в числовом порядке. Патч 06 требует 02. Патч 07 дополнительно требует
PR60 `core/01-borrowed-transcript-parts.patch` из пакета
`performance/2026-10-29/borrowed-payloads-and-build-inputs/` (точный SHA в
SOURCES.json); не применяйте его отдельно к чистому upstream. Патчи не зависят
от ещё не опубликованного Core API/фиктивного
Cargo pin. Внешние upstream репозитории этой доставкой не меняются.

Для совместного применения с [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60)
берётся его head `2f32b832b3430950cd43bd7f4ccba5ad34213811` с 17 патчами.
Изменения PR58/59 уже перенесены в закреплённые upstreams, повторять их не нужно.
Не переносите утверждение о совместимости на произвольные будущие commits.

## Навигация и статус доставки

Сверка 30 октября 2026, 15:32 UTC; состояния PR и факт наличия кода — разные вещи.

| Набор | Delivery-статус | Что делать на текущем upstream |
|---|---|---|
| [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60) и [PR61](https://github.com/Qweasd123tg/proteus-modules-dot/pull/61) | merged; main `73d438d49…` | Исторические 25 patches уже портированы; не применять повторно. Этот 08 исправляет только неполный delivery artifact. |
| [PR62](https://github.com/Qweasd123tg/proteus-modules-dot/pull/62) | open draft, head `a8f53154…` с отчётом PORTED; не слит в delivery main | Все 6 изменений перенесены upstream; пользовательские fixture/docs refinements сохраняются. Draft-статус не означает отсутствие кода upstream. |
| [PR63](https://github.com/Qweasd123tg/proteus-modules-dot/pull/63) | open draft, head `6ca100ed…`; не слит в delivery main | Два новых отдельных source-патча: terminal receipt и streaming Extensions ZIP. Их свежие базы и gates не относятся к этой исторической серии. |
| Отдельные alpha API proposals | Не опубликованы отдельным delivery packet/PR | Не являются частью этого пакета или PR62; требуют собственной согласованной интеграции и настоящих consumer pins. |

[SHA256SUMS](SHA256SUMS) фиксирует все 8 patches, этот README и SOURCES.json;
сам checksum-файл не хеширует себя. Проверка суммы не заменяет review или tests.

## Evidence и границы

Авторское и независимое source review, проверка preimages, strict apply/reverse
и candidate byte comparisons выполнены. После поправки 08 проверены 74 точных
preimages; композиция всех 25 patches (17 прежних + 8 новых) проверена с точным
reverse. Regression sources добавлены, но
**Успешное выполнение Rust tests/builds, UI, CI или benchmarks не подтверждено**.
Static application не подтверждает компиляцию. Нет измеренных latency/CPU/RAM
цифр. Требуемые executable gates остаются в существующих Core guides.

Согласованные typed-helper/runtime-feature API proposals и новый opt-in
observer — отдельные направления, а не скрытые зависимости этих patches.
После выпуска этого пакета исследование продолжается; подтверждённые новые
изменения доставляются отдельными понятными дополнениями.

При отделении defaults от effective state проверяйте не только setters и
save/reload, но и все clone/inherit/session-create consumers вместе с уже
существующими assertions: AppConfig не должен неявно переносить session override.
