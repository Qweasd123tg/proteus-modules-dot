# Однократное получение terminal result после вытеснения index entry

Source-кандидат для [Core
`befd30516aefa6f0a0ad5db9924ad4957160b8dc`](https://github.com/Proteus-harness/Proteus-core/tree/befd30516aefa6f0a0ad5db9924ad4957160b8dc).
Патч: `terminal-outcome-claim.patch`, SHA-256
`cb8f5fd57d9ff4f63074bcb0186c9088f98e57f71332716c4c6a819255f6f036`.

**`successful_executable_validation_evidence: false`**.
Исходники и статическая применимость проверены; успешная компиляция,
тесты, runtime, CI и benchmark этим пакетом не подтверждены.

## Дефект и граница исправления

`ProcessAgentControl::wait` уже получает `Arc<PendingOutcome>` до ожидания.
Пока оно ждёт, monitor может завершить ребёнка, а следующий `reserve` —
вытеснить готовую запись из bounded pending index. Прежний `consume(spawn_id)`
снова требовал запись index и терял возможность вернуть уже полученный outcome.

Claim теперь принадлежит самому shared outcome: `result` и `consumed` защищены
одним mutex. Уже полученный Arc можно потребить **не более одного раза**, даже
после index eviction. Удаление index entry происходит только при `Arc::ptr_eq`,
поэтому старый waiter не удалит новую запись с тем же текстовым spawn ID.

- Попытка до готовности не потребляет результат.
- Из двух получивших один Arc waiter-ов только один успешно делает claim.
  Это относится и к child error: первый возвращает исходную ошибку ребёнка,
  второй получает ошибку уже потреблённого результата.
- Drop pending wait не вызывает claim; JoinHandle по-прежнему принадлежит
  отдельному monitor. После завершения `outcome.wait()` и до claim нет нового
  `await`. Это не обещает exactly-once доставки результата внешнему получателю.
- Новый waiter после eviction по-прежнему не находит handle. Active cap,
  oldest-ready eviction и невытесняемые control-plane entries не меняются.
- Outcome уже удерживался acquired Arc ранее; новый cache, durable store или
  неограниченный discovery index не добавлены. Result живёт до освобождения
  его оставшихся owners.

Это **владение receipt**, а не доказательство остановки всех descendant effects
и не разрешение очищать worktree. Cancellation ACK не превращается в terminal
worker settlement. Worktree ownership — отдельное изменение.

## Независимая статическая проверка

Все три исходных blob сверены с current upstream tree; strict
`git apply --check --whitespace=error-all`, применение, candidate-byte comparison
и обратное восстановление выполнены. Прямой установленный rustfmt проверил
оба изменённых Rust-файла, edition 2024, `skip_children=true`; exit 0.

Source review проверил:

1. Одно mutex-состояние для readiness/claim и единственного победителя.
2. Pointer-guard удаления при eviction/replacement; прежние caps не ослаблены.
3. Drop pending wait и terminal-error path без преждевременного consume.
4. Notify registration перед чтением state; нового lost-wakeup окна нет.
5. Порядок registry → outcome lock; completion не захватывает registry.
6. Возврат результата production consumer только после успешного claim.

Четыре новых deterministic regression sources покрывают eviction после
acquisition, единственного потребителя terminal error, replacement pointer и
drop pending future. Они не являются выполненным concurrency/stress gate.
Source-level blocker в этой ограниченной правке не найден.

`SOURCES.json` содержит точные baseline/candidate identities, публичные ссылки,
source-review summary и выполненные статические проверки. `SHA256SUMS` покрывает
README, manifest и неизменённый reviewed patch.

## Применение и остающиеся gates

Патч применяется непосредственно к указанному Core commit; prerequisites из
других delivery packets нет. Pre-lease cancellation fix уже upstream и не
должен применяться повторно. После изменения upstream нужен новый review,
а не forced/zero-context application.

После разрешения на execution: focused Core pending tests, затем применимые
реальные process-agent pool/control boundaries через существующий runner и
актуальные fixtures, согласно [Core testing
guide](https://github.com/Proteus-harness/Proteus-core/blob/befd30516aefa6f0a0ad5db9924ad4957160b8dc/docs/development/testing.md).
Formatter не заменяет эти gates. Нет измеренных latency/RSS/CPU claims,
deployment или новых разрешений на запуск кода.
