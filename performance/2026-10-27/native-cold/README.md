# Native cold recovery: проверка инструмента и синтетических корпусов

**Статус исходников: AUTHORED, NOT EXECUTED.** Это новая реконструкция.
Прежний неопубликованный memory-only прототип не восстановлен; его hashes
не относятся к этому пакету. Наличие исходников не является результатом прогона.

## Источники и граница

Одинаковый native_cold_probe.rs накладывается только на одноимённый новый
example в двух disposable checkout Core:
A e9d6bd06df78a5af85d055117a6697187730e30e;
B 63454d4e8b1e4e6b26d088fce2a17d46f30390ae.
Production-путь — cold writer initialization и отдельная strict projection.
Схема журнала, durability barriers, policy, providers, UI и пользовательские
данные не меняются. Живых моделей или module invocations в самом probe нет.

Reference fixture для canonical tests отдельно собирается на Modules
7fceaebc3bed8add9b0e3091110f59deca86ba46. Наличие sibling/override не доказывает
pin: prepare.py проверяет Git HEAD, чистоту входов, равенство Core Cargo.lock,
compiler version, hashes overlay и реальные executable paths из Cargo.
Rust 1.95.0, locked dependencies, release profile и отдельные target dirs.

## Этап 1: qualification

Push в точную экспериментальную ветку запускает только qualification.
На обоих Core выполняются canonical scripts/test.py:
- -p proteus-core --lib core::session_journal
- -p proteus-core --lib core::session_store
- -p proteus-core --test session_writer_lock

Пустой test filter — ошибка. В session_store должен присутствовать существующий
cold-reopen case usage_tracks_exchanges_and_matches_read_only_cold_journal.
Это focused gates, НЕ full workspace/replay/runtime/UI pass.
Сборки и эти gates не входят в 600 секунд собственно эксперимента.

Launcher калибруется тем же fork/exec путём, что и SUT. Три повтора:
low/high parent × touched native child allocations 0/32/128 MiB.
192 MiB parent allocation остаётся живой при запуске. GNU time снимает peak RSS
собственного непосредственного SUT child: значение должно зависеть от allocation
ребёнка, но не parent. Python wait4 обязан показать parent-memory floor/delta
и сохраняется ТОЛЬКО как diagnostic, никогда как RSS SUT.
Forked child, удерживающий pipe после выхода leader, проверяет timeout cleanup.
Допуски относятся к инструменту, не к целевой скорости продукта.

Каждый корпус содержит 16 MiB ЛОГИЧЕСКОГО исторического текста:
- inline: 128 уникальных history replacements × 128 KiB;
- blob: 32 уникальных replacements × 512 KiB.

Фактический storage encoding проверяется. Уникальные obsolete message/part IDs
и content исключают shortcut с одним deduplicated blob. После замен добавляются
семь небольших lifecycle facts: root turn, успешный usage, context-window error,
незавершённый exchange и cancellation. Это синтетический obsolete-snapshot
stress, НЕ реалистичный средний разговор.

ФИЗИЧЕСКИЙ размер каждого корпуса вместе с oracle ограничен 64 MiB; размеры
и SHA-256 каждого файла сохраняются. JSON/envelope overhead не называют
логическими 16 MiB. B не создаёт независимый seed: обе версии получают
byte-identical copies одного baseline corpus.

Seed заранее фиксирует continuation и его canonical identities. Oracle содержит
все hydrated records/envelopes, history, conversation/model-context, usage и
interruption state. Дополнительно проверяются буквальные ненулевые ожидания:
Usage 1200, ContextWindowExceeded 100000, Completed/Error/Canceled.
Нормализовать можно только record ID и timestamp НОВОГО appended envelope.
Старые envelopes, message/part IDs, usage times и context сравниваются точно.
Continuation не записывает сам себе ожидаемый ответ.

Отдельный untimed audit cold-appends и читает usage из того же живого writer.
Public conversation read восстанавливает strict context, а не private live
model-context cache. Существующий canonical cold-reopen test защищает cache
отдельно; это НЕ прямая эквивалентность cache на данном stress corpus.
Production accessor ради benchmark не добавляется.

В qualification дополнительно выполняются восемь smoke arms: оба корпуса ×
recover/projection × оба бинарника. Они проверяют настоящий measurement path,
stdout schema, journal prefix/lease bytes и cleanup. Их отдельные metrics
помечены как smoke, не как сравнительные performance results.

## Этап 2: измерения после принятой qualification

Только явно согласованный workflow dispatch с measure=true и expected_head,
равным полному SHA проверенного bundle commit, включает измерения:
10 A/A и 10 A/B пар на каждый корпус и mode, по пять прямых и обратных порядков.
В A/A обе arms используют один и тот же SHA бинарника A. Каждый запуск —
новый process и новая проверенная копия. Seed остаётся неизменным.

recover измеряет первый durable append ПОСЛЕ SessionStore::open.
projection измеряет построение и удержание полной strict projection.
Rust Instant исключает fixture parsing, Tokio startup, open, stdout и 100 ms
retention. GNU-time RSS включает всю жизнь SUT. Python process wall отдельно
включает startup/retention. PSS, process-tree sum и parent wait4 не подменяют RSS.

Каждая arm затем проверяется отдельным untimed process. Projection не меняет
ни одного файла; recover сохраняет точный journal prefix, добавляет одну запись
и обновляет только journal.write.lock до точных pid=SUTpid bytes. Другие файлы
не меняются. Удаляются только собственные disposable arm copies
после проверки; seeds, manifests, binary hashes и compact raw rows сохраняются.
Перед созданием корпусов hosted runner требует минимум 2 GiB свободного диска.

Hashing/copying предварительно читают страницы: fresh process НЕ cold OS cache.
Не заявляются cache dropping, CPU isolation, thermal stabilization,
репрезентативная interactive workload или скорость модели/агента/всего клиента.
Paired medians/ranges — описательные данные с числом пар и A/A spread.
Нет pass/fail speed threshold, надёжного p95/p99 из 10 пар или общего speedup.

## Ограничения и отказы

Experiment: whole-run alarm 600 s, deadline одного child 60 s, combined stdout/
stderr 32 MiB, oracle input 32 MiB, compact report 4 MiB. Core dumps отключены;
CPU time ограничен. Exceptional exit launcher-а завершает свою process group,
включая pipe-holding descendant после выхода leader. Это не универсальный
containment для программы, специально выходящей в другую session.

Preparation имеет отдельные command deadlines 20 минут, workflow ceiling
60 минут. Failures остаются failures, не skip-pass. Report различает qualification
и measurements и сохраняет partial rows со статусом FAIL. Отсутствие evidence
означает NOT EVALUATED.

Пакет предназначен только для отдельно согласованного draft branch
Qweasd123tg/proteus-modules-dot. Он не разрешает upstream writes, merge,
release, production execution или публикацию private reports.
