# Согласованность runtime и работа после reset

Source-only изменения Core на
`925de0fc5ee5995409b11e42b216a15ca12f76d0`. Это продолжение работы над
фундаментом, не заявление о завершённой оптимизации проекта.

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

## Применение

`SOURCES.json` фиксирует исходные Git blobs, candidate hashes и порядок
проверенной композиции. Патчи относятся к Core checkout, а не к delivery repo.
Сначала проверяйте `git apply --check --whitespace=error-all`, затем применяйте
в числовом порядке. Они не зависят от ещё не опубликованного Core API/фиктивного
Cargo pin. Внешние upstream репозитории этой доставкой не меняются.

Для совместного применения с [PR60](https://github.com/Qweasd123tg/proteus-modules-dot/pull/60)
берётся его head `2f32b832b3430950cd43bd7f4ccba5ad34213811` с 17 патчами.
Изменения PR58/59 уже перенесены в закреплённые upstreams, повторять их не нужно.
Не переносите утверждение о совместимости на произвольные будущие commits.

## Evidence и границы

Авторское и независимое source review, проверка preimages, strict apply/reverse
и candidate byte comparisons выполнены. Отдельно проверены 61 fresh preimage и
композицию всех 22 patches (17 прежних + 5 новых) с точным reverse. Regression sources добавлены, но
**Успешное выполнение Rust tests/builds, UI, CI или benchmarks не подтверждено**.
Static application не подтверждает компиляцию. Нет измеренных latency/CPU/RAM
цифр. Требуемые executable gates остаются в существующих Core guides.

Согласованные typed-helper/runtime-feature API proposals и новый opt-in
observer — отдельные направления, а не скрытые зависимости этих patches.
После выпуска этого пакета исследование продолжается; подтверждённые новые
изменения доставляются отдельными понятными дополнениями.
