# Capture writer: уведомления вместо timeout polling

Source-only candidate для `Proteus-harness/Proteus-modules` commit
`200d1ec54f1217f61a31823db939df3799c638dc`. Нет дополнительных patch prerequisites,
Cargo/pin/lock/API изменений или новых settings. Независимое source review: PASS
для patch `059e6194e8bc4938949872fa94df1164a2febfe0c3d9ce462cb221b6d8f7c91f`.

## Изменение

Существующий writer проверяет terminal facts через `recv_timeout(20 ms)`.
Candidate сохраняет bounded sync_channel на восемь chunks и добавляет Condvar
на существующий state mutex. Writer под mutex проверяет failure и `try_recv`;
при пустой очереди и незавершённых readers атомарно освобождает mutex в wait.
Enqueue, reader end и abort меняют predicates под тем же mutex и уведомляют
writer. EOF/failure не занимают data queue slot и не теряются при queue-full.

Это исключает намеренный периодический timeout wakeup и ожидание следующего
poll после terminal notification. Это source-level устранение работы, не
измерение CPU/latency/RAM. Один writer thread на capture остаётся.

## Инварианты

- Между проверкой пустой очереди/terminal predicates и wait нет окна для
  потерянного notification: publisher должен получить тот же state mutex.
- Spurious wake приводит к повторной проверке; notify до старта writer тоже
  безопасен, поскольку state и queue сохраняют predicate, а не только сигнал.
- Не меняются queue capacity, chunk cap, raw counter, preview, failure labels,
  необратимость overflow, complete_stream или retention/authority checks.
- Failure проверяется прежде dequeue/seal. Seal требует закрытых readers,
  пустой очереди и confirmed==queued. Последний chunk не пропускается.
- Append остаётся вне state mutex. File ownership/drop order и reservation
  сохраняются; abort не делает blocking OS I/O preemptible.
- Нет отдельной control queue, polling fallback или shared global state.

## Regression sources

Новый `capture/tests/writer_wake.rs` использует test-only wrapper над private
writer loop с no-op production hook перед atomic wait. Channel handshake
показывает, что writer достиг wait boundary; тест не угадывает это через sleep.

Сценарии: enqueue на wait boundary и EOF после финального dequeue; spurious
notification и empty EOF; последний chunk+EOF до запуска writer; abort без EOF;
protocol failure без EOF; queue-full failure без ложного seal. Существующие
queue-full/preview, partial-write и binding-drop tests сохраняются.

Assertions ждут сигналы с 5-second deadline; RAII abort+join не оставляет worker
после assertion unwind. Это не hard timeout всего test: зависание внутри ОС или
ошибка самого shutdown протокола требуют outer test-runner timeout. Test hook
не запускает внешние команды и не является публичным API.

## Статические проверки и ограничения

Прочитаны pinned AGENTS и полный fresh-tree source identity evidence. Все четыре
preimage blob совпадают с pinned Modules tree; новый regression file отсутствует
в fresh tree. Direct installed rustfmt используется только для parsing/format;
strict forward/reverse apply проверяются отдельно. Численные performance claims
и успешные executable gates не заявляются. Tests, scripts, Cargo, build, CI и
project execution не запускались. Upstreams не изменялись.

Перед adoption нужны shell-tool capture unit/integration и lifetime gates в
разрешённой среде. Независимое review — `REVIEW.md`, checks — `SOURCES.json`.
