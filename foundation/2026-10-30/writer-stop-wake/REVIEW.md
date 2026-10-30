# Независимое source-only review

Принят точный patch SHA256
`aecf20dd48bdaf75b7a44ef454c499d21247b7571287a8f8dd2a71757e1ed491`
на Core `befd30516aefa6f0a0ad5db9924ad4957160b8dc`.

Независимый reviewer сверил writer, transport, lifecycle и wake с исходными
Git blob identities. Подтверждён достижимый порядок: stop прочитан как false,
все завершающие уведомления уже прошли, writer считывает новую revision и
засыпает с подключёнными senders; join не обязан завершиться. Перенос snapshot
revision перед Acquire stop-check закрывает именно этот промежуток. Порядок
очередей и остальная обработка не меняются.

Reviewer отдельно сверил финальный session source и применил точный patch
к свежим baseline writer/session: forward check, применение, побайтовое
сравнение с candidate и reverse check прошли. Дополнительная финальная
проверка упаковки подтвердила rustfmt двух файлов и строгую композицию
с broker patch PR71 в обоих порядках; результаты в `COMPOSITION.json`.

Добавлен один сценарий настоящего ProcessTransport с сохранённым writer clone
и предварительно завершённым/reaped child. Watchdog ожидает завершение
terminate/join три секунды. Он не форсирует прежний race, не доказывает падение
baseline, не освобождает зависшие worker/helper threads и не ограничивает
начальное lifecycle termination. Нужен внешний timeout тестового процесса.

Решение: допустим подготовительный draft с указанными ограничениями.
Compilation, type checking, tests, Cargo, CI, mock child и product runtime
не запускались. Это не runtime-pass, не доказательство общей liveness или
совместимости всего стека. Runtime gate перед merge остаётся открытым.
