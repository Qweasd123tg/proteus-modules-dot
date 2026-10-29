# Source-side output capture — прототип Rust

**Новая дельта:** ограниченный artifact tap непосредственно в reader stdout/stderr,
до создания полного `ToolResult` и RPC. Существующий head/tail collector Proteus
не переписан: `read_step` передаёт ему тот же borrowed chunk через callback.

**Статус:** исходники отдельной std-only библиотеки, не production module.
Сборка, тесты, rustfmt, CI и исполнение написанного/upstream кода **не выполнялись**.
Проведён только ручной обзор исходников. Upstream не изменён; remote publication
не выполнялась. Производительность и совместимость исполнением не установлены.

## Что реализовано

```text
host-owned pipe reader (fixed 16 KiB scratch)
  → StreamCapture.observe(&chunk) → optional trusted, capped artifact sink
  → existing bounded preview collector
  → finish(reader end, original command outcome)
  → fixed-size receipt + existing bounded ToolResult/RPC adapter
```

- `read_step` делает один read в предоставленный host буфер. Сам capture не хранит
  output, не строит `String`, не вызывает `Command`, не открывает файлы.
- `StreamCapture::preview_only` — без sink и без дисковых записей.
- `with_artifact` проверяет scope sink; ceiling = `min(requested_cap,
  reserved_bytes)`. На ошибке scope объект sink возвращается host без записи.
- `observe` предлагает sink только префикс chunk, помещающийся в оставшийся cap.
  При исчерпании cap или ошибке sink дальнейший вывод всё равно учитывается и
  передаётся существующему preview collector; host должен продолжать дренирование.
- После append failure больше нет append/seal/reopen/retry. Известный частичный
  результат и неопределённый эффект учитываются раздельно. Команда не повторяется.
- `finish` потребляет capture. Только успешный seal с правильными scope и длиной
  возвращает opaque artifact ID и подтверждённый диапазон `[0, readable_bytes)`.
- Scope: session + invocation + capture + stream. Идентификаторы фиксированной
  длины не являются путями, разрешениями или самоподписанными capabilities.

`observe` можно подключить прямо к существующему async reader без `read_step`.
Нельзя сначала собрать весь output, а затем вызвать `observe`: это опять post-hoc.
`read_step` — иллюстрация ограниченного чтения, не готовая замена reader lifecycle.

## Значение результата

| Поле | Семантика |
|---|---|
| `status = Captured` | Все **наблюдённые** bytes опубликованы; поток ещё мог быть прерван |
| `Truncated` | Опубликован префикс; дополнительные наблюдённые bytes не вошли в cap |
| `Failed` | Append/seal либо проверка receipt не удались; читаемая ссылка не выдаётся |
| `Disabled` | Host не предоставил artifact sink; preview остаётся отдельным механизмом |
| `source_end` | Настоящий EOF / interruption / read failure / unknown, независимо от sink |
| `command` | Исход **исходной команды**, переданный host независимо от capture |
| `confirmed_appended_bytes` | Подтверждённые append-операции; на failure это не обещание durability |
| `unconfirmed_append_bytes` | Верхняя граница последнего append с неизвестным эффектом |
| `cap_reached` | Подтверждённые appends дошли ровно до cap; не доказательство усечения |

Ровно `cap` bytes + EOF → `Captured`, а не `Truncated`.
`cap + 1` → `Truncated`; при cap=0 пустой поток может быть полным, непустой — нет.
Счётчик имеет явный `saturated`; переполнение не выдаётся за точный размер.
`is_complete_stream_artifact()` требует и `Captured`, и настоящего EOF.

EOF stdout не доказывает завершение команды или EOF stderr. Exit code 7 не
превращается в capture failure; disk-full не заменяет exit code команды. Запрос
cancel/timeout сам по себе не подтверждает kill: host передаёт `Running`/`Unknown`
до фактического наблюдения termination. Публикация неполного потока разрешена,
но его `source_end` должен сохраняться и быть виден читателю/model adapter.

## Граница доверия и обязательства интеграции

`TrustedArtifactSink` — **явно переданный объект host**, а не путь из ответа модели.
В crate намеренно нет реализации файлового sink, `Path`, `fs::write`, автоматического
`impl` для `Write` или доступа по artifact ID. Rust-типы сами по себе не авторизуют
операции: их нельзя напрямую десериализовать из model arguments и считать trusted.

Host должен обеспечить:

1. **До выдачи sink:** авторизацию владельца, per-session/global reservation,
   предел числа artifacts, секретов/retention policy. Локальный ceiling не заменяет
   атомарный quota manager; для двух потоков бюджеты резервируются совместно.
2. **Хранение:** отдельное capture storage, безопасное создание без symlink/TOCTOU,
   права доступа, точный append contract, seal/durability, quarantine частичных
   записей после ошибки; Drop не повторяет записи и не публикует failed capture.
   Если seal завершился неопределённо, receipt не объявляет artifact доступным;
   host reconciliation возможен без повторного запуска команды.
3. **Reader lifecycle:** параллельное дренирование stdout/stderr, реальные deadlines,
   cancellation, shutdown и закрытие writers. Exit+drain grace ≠ EOF. Синхронные
   `Read`/sink могут блокировать; этот прототип не прерывает заблокированный IO.
   Для async-очереди нужны отдельный bounded byte budget и backpressure policy;
   unbounded channel уничтожит гарантию ограниченной памяти.
4. **Ошибки и объём:** продолжение drain после disk-full/cap, без бесконечного
   ожидания бесконечно пишущего процесса; лимиты времени/CPU — вне capture.
   Нельзя превращать capture failure в автоматический повтор mutating command.
5. **Чтение:** проверку session/invocation/tenant и доступного диапазона на каждый
   запрос; bounded pagination, а не выдачу произвольного пути или всего файла.
6. **RPC:** adapter существующего ToolResult, bounded UTF-8/JSON rendering с учётом
   escaping/omission markers/metadata. Здесь нет wire schema, exports или нового
   process slot. Размер serialized frame этой библиотекой не доказан.

При host crash/Drop до `finish` терминального receipt нет: это не success и не
основание повторить команду. Host-owned reconciliation/retention остаются отдельными.
Если `append` паникует и host перехватывает unwind, capture остаётся `Failed`
с неопределённым эффектом предложенного chunk, а не `Disabled`; автоматического
catch/retry здесь нет. Panic/abort во время `seal` может оставить результат публикации
неизвестным и не выдаёт receipt: требуется host reconciliation. Panic и последующее
продолжение reader нельзя превращать в ложный EOF или повод повторить команду.

Capture sink может содержать sensitive output — сохранение на диск меняет retention,
поэтому оно не включается только по факту, что модель попросила большой вывод.

## Точка подключения и отличие от предыдущего исследования

В Modules `5fa8978684a37e8083c64f4d6cf0289e72450c6a` shell уже имеет bounded
head/tail, `dropped_bytes`, `truncated`, `exit_code`; это не новая оптимизация.
`research/tool-output-artifacts` принимает готовый `ToolResult`: он не предотвращает
предварительную materialization и не является source capture.

Этот прототип предназначен для **reader path существующего shell-tool** до его
session buffer, а не `AfterTool` hook. Периодические `wait_and_collect` не должны
пересоздавать capture: один capture живёт до закрытия соответствующего потока.
Для интерактивных сессий надо явно выбрать ownership, lifecycle и способ выдачи
текущих, ещё не sealed snapshots; этот API выдаёт только терминальный receipt.

Уменьшение peak RSS относительно уже bounded collector не заявляется. Полезная
добавка — доступ к capped artifact-префиксу без полного RPC output. Память самого
capture не растёт с объёмом потока; память/очереди sink и preview — контракт host.

### Основа ручного обзора

- [Текущий shell output](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/tool/shell-tool/src/unified_exec/output.rs).
- [Предыдущий post-hoc artifact prototype](https://github.com/Proteus-harness/Proteus-modules/blob/5fa8978684a37e8083c64f4d6cf0289e72450c6a/research/tool-output-artifacts/src/lib.rs).
- [Deep Agents source-side capture](https://github.com/langchain-ai/deepagents/blob/cd24d8c52849fdb24e0ac2cab2f909f8df6ba5ca/libs/deepagents/deepagents/backends/sandbox.py#L1367-L1461): идея seam, не буквальный перенос shell wrapper.
- Основание: [OpenHands / Deep Agents](../../reports/openhands-deepagents.md).

Ниже — **план проверки, не результаты исполненных тестов**: пустой/нулевой/exact-cap/
cap+1 поток; chunk больше cap; несколько read chunks; successful и uncertain partial
append failure; seal failure/wrong scope/wrong length; invalid UTF-8; EOF при Running;
cancel/read failure при exit 0; сохранение code 7 при disk-full; неизменный preview
после cap/failure; отсутствие повторных append/seal после failure; caught append panic; квоты двух потоков;
blocked IO/cancellation в настоящем host adapter. Исходники требуют отдельной сборки,
контрактного review sink и исполнения этих сценариев до production adoption.
