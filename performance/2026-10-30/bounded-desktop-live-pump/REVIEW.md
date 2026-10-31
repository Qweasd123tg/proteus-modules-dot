# Независимое ревью: ограниченная обработка live-потока

Основа Desktop: `a28cc7f507424a570e86dc44230ee323156fdf6c`.
Патч SHA256: `ada1f395c3ecaaf16723a16d2cd8d60a6fa6cb65cca9537e637ae90558ba3f9b`.
Нормализация затронула только old-path заголовка нового файла: обратная замена воспроизводит исходный проверенный SHA256 `0e6c7b68738089f542cbf980cb9590eb4479c64292d4680955e2c9767b4ad233`. Содержимое production/test изменений не поменялось; reverse apply --check и совпадение публичной копии проверены независимо.

**Блокирующих замечаний по исходникам не найдено.** Это поддерживаемый путь работы, в отличие от отложенного предложения об изменяемых action контролов.

## Подтверждённая проблема

`connection::spawn_pump` передаёт события SSE из отдельного потока в неограниченный async_channel. Live pump забирает все доступные события через `while try_recv`, а затем применяет их синхронно. При постоянно пополняемой очереди этот участок не имеет верхней границы числа событий. Даже ограничение одного Vec без явного возврата Pending недостаточно: следующий `recv().await` может сразу вернуть Ready и цикл продолжится в том же poll. Начальная загрузка уже ограничена 256 событиями.

## Что проверено в изменении

- `ready_batch` берёт первое уже полученное событие и не более 255 следующих; не ждёт заполнения бюджета. Остаток остаётся в исходной FIFO-очереди, без дополнительного чтения, отбрасывания или перестановки.
- После успешного применения каждой порции `yield_after_batch` один раз вызывает wake_by_ref и возвращает Pending. Следующий poll продолжает работу. Нет таймера, задержки заданной длительности, detached task или сохранённого владельца waker.
- Ошибка обновления завершает прежнюю задачу. Владение receiver и отмена задачи не перенесены в другие объекты.
- Разбиение text-run изменяет только длину допустимой группы. Прежние cursor gates, исходные envelopes, journal/terminal события и все нетекстовые barriers остаются; обработчик barriers не изменён. Дополнительные границы могут увеличить число промежуточных materialization/notify — это компромисс для ограниченного poll, не заявление об ускорении throughput.

## Почему Pending даёт реальную возможность диспетчеру

Cargo.lock закрепляет `gpui-fast 0.1.12`, checksum `87b6d2f355531132e8f1ec357cb23901aba1d1b3e522260822ae199f02ec32da`. Для анализа прочитан соответствующий upstream tag v0.1.12, разрешённый в commit `07b42ebf1f43088b8b74a7d4fca6b95e44e04265`:

- [ForegroundExecutor](https://github.com/longbridge/gpui-fast/blob/07b42ebf1f43088b8b74a7d4fca6b95e44e04265/crates/gpui/src/executor.rs) использует LocalExecutor; [PlatformScheduler](https://github.com/longbridge/gpui-fast/blob/07b42ebf1f43088b8b74a7d4fca6b95e44e04265/crates/gpui/src/platform_scheduler.rs) передаёт runnable в dispatch_on_main_thread.
- [Linux](https://github.com/longbridge/gpui-fast/blob/07b42ebf1f43088b8b74a7d4fca6b95e44e04265/crates/gpui_linux/src/linux/platform.rs#L174-L205) запускает foreground runnable как idle callback после pending events; возврат из runnable также позволяет вызвать after_runnable.
- [Windows](https://github.com/longbridge/gpui-fast/blob/07b42ebf1f43088b8b74a7d4fca6b95e44e04265/crates/gpui_windows/src/platform.rs#L1308-L1375) проверяет бюджет 10 мс между runnable, затем обрабатывает paint/input. Одна бесконечная poll не возвращает управление этой проверке.
- [Apple](https://github.com/longbridge/gpui-fast/blob/07b42ebf1f43088b8b74a7d4fca6b95e44e04265/crates/gpui_apple/src/dispatcher.rs#L51-L56) ставит runnable асинхронно в main queue.

Это подтверждает кооперативную границу задачи и возможность внешней обработки событий, **не** гарантирует отдельный кадр между порциями, равную долю времени для задач или предел latency. Сверка байтов опубликованного crates.io-архива с tag не выполнялась; версия, lock checksum, commit и blob-источники сохранены раздельно.

## Проверки и ограничения

Три preimage независимо получены по commit Desktop и побайтово сверены. Whitespace-проверка прошла. Прочитаны четыре новых теста: FIFO/остаток/barriers; неполная порция; UTF-8 коррекция и reducer oracle через границы; ручной poll Pending→Ready с одним wake. Их ожидания согласованы с исходниками. Старые тесты barriers/reconnect/observer effects сохранены.

Тесты, проектные скрипты, Cargo, сборка, CI и нативное приложение **не запускались**. Ручной poll тест не доказывает фактическую частоту кадров. Нужны разрешённые Rust-проверки и нативная проверка под длительным потоком: ввод/прокрутка/закрытие, получение terminal событий, reconnect и точный итог transcript.

Ограничено число событий в одном poll, а не байты, длительность отдельного события или общая память очереди. Unbounded channel остаётся; sustained producer overload может увеличивать backlog. Один большой snapshot по-прежнему способен занимать значительное время. Это не исправление backpressure и не замер RSS/CPU/latency.
