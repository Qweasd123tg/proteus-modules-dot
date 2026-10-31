# Независимая проверка окончательного patch

Проверен только окончательный patch SHA256
`80def7b6bc48aa6abf96a3a679c2b71800204df8bb73a7bac50d20b982624280`.

Подтверждена цепочка ContextDispatcher → ProcessContextProvider →
ProcessExportClient → общий ComponentBroker и освобождение последнего владельца
в finish/reset на потоке broker. Слабая ссылка invocation scope не заменяет
сильное владение внутреннего dispatcher. Invocation/cancel handles удерживают
command sender, а не BrokerInner.

Окончательный patch сохраняет обычный внешний FIFO Shutdown+join и использует
stop+wake только при self-thread destruction. Порядок revision → stop check
согласуется с mutex/revision/Condvar реализацией ProcessWake. Pending terminal
settlement, generation filtering и cleanup остаются существующими.

Явная граница: stop проверяется основным циклом; уже выполняющийся обработчик
может продолжиться. В частности, finish(A) после освобождения final-owner
dispatcher A может вызвать admit_queued_roots и активировать ожидающий B до
выхода из цикла. Независимый handle B не удерживает BrokerInner. Patch не вводит
центральный admission barrier и не обещает немедленного no-new-dispatch,
no-new-effect или quiescence. Это совместимо с ограниченным продолжением
обработчика при асинхронном внешнем Shutdown; обычный reset и settlement
pending-вызовов не изменены.

Регрессионные исходники проверены на детерминированность, отсутствие запуска
process и ограниченные watchdog ожидания. Единственный прежний вызов
LoopState::run и прямой initializer BrokerInner обновлены.

Независимо пройдены проверки identities, forward/reverse apply, whitespace,
совпадения дерева и rustfmt. Нерешённых source-review блокеров не выявлено.
Это готовность пакета к review, **не** подтверждение компиляции, прохождения
tests, runtime cleanup, effect quiescence или готовности к merge.
