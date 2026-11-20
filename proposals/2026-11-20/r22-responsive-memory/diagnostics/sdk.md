# Диагностика SDK для R22

Локальный стенд, не продуктовая оптимизация. SDK-патч накладывается на
`Proteus-core@0c1b7572313230e5d123e95c722e1258a2e9ecd6` (именно этот pin
использует `Proteus-modules@cf999371f6e564376565738bebc3416aad12f908`).
В отдельной копии Modules дополнительно применяется `state-trace.patch`. В
одноразовом рабочем каталоге `build.sh` задаёт Cargo path overrides для этого же
source checkout; внешний backend Core никогда не пересобирается/не подменяется.
В `deps.txt` проверяем, что и SDK, и общие DTO взяты из этого дерева. Пакеты из
registry не обновляются; изменение Cargo.lock в Modules удаляет git source ID
именно у шести локальных packages и добавляет SDK dependency на уже закреплённый
libc. Бинарник запускается обычным способом.

* При отсутствии `PROTEUS_SDK_TRACE_PATH` SDK не открывает файл, не берёт
  диагностические timestamps и не ставит wrapper под штатный BufWriter. Проверки
  thread-local флага у границ фаз остаются. Для A/B используйте исходный
  неинструментированный бинарник. При опции один JSON-объект на строку пишется
  в append-файл после терминального ответа, вне stdout mutex. Путь должен
  принадлежать организатору теста; при повторе используйте новый файл. Время,
  PID, канонический ID вызова, безопасная метка операции, размер кадра и исход;
  нет значений DTO, путей, токенов или входных меток вне allowlist.
* Linux: CLOCK_MONOTONIC ns, те же единицы/начало отсчёта, что у Python
  time.monotonic_ns(). На других платформах `clock` явно помечает локальную шкалу
  процесса: нельзя напрямую вычитать время из Python. Связка в пределах одного
  поколения worker: wire `id` ↔ SDK `pid,id` ↔ State `pid,id`. Журнал admission
  capacity errors и failure to spawn не охватывает.
* Фазы с `*_ns`, кроме `sink_*`, являются метками, не длительностями. Разности:
  dispatch_start−admitted = spawn/schedule + bridge setup;
  storage_start−dispatch_start = SDK lookup, DTO decode/validation;
  value_start−storage_start = backend execute (включает State);
  value_end−value_start = typed result → serde_json::Value;
  count_start−dispatch_end = terminal envelope/branch;
  count_end−count_start = обязательный size preflight;
  stdout_lock−count_end = ожидание writer mutex;
  encode_end−stdout_lock = JSON serialization + newline + все вызванные до flush
  записи; flush_end−encode_end = вся стадия BufWriter.flush().
  Внутри serialization `sink_write_ns_at_encode_end` измеряет время, проведённое
  в реальном downstream Write::write, а не в serde; вычитание даёт остальной wall
  time, не CPU time. `sink_write_ns` суммирует **все** downstream writes;
  `sink_flush_ns` только вызов нижнего Write::flush. Время downstream
  перекрывается с encode/flush: не складывать их повторно. Это вызовы Write у
  std::io::stdout, не счётчик kernel syscalls. `frame_bytes` включает newline
  (relay bytes без него). Null = стадия не достигнута. Недописанный/оборванный
  вызов не считается успешным измерением.
* Smoke: `PYTHONDONTWRITEBYTECODE=1 python3 smoke.py` на Linux. Сравнивает
  детерминированную выдачу stock/off/on, проверяет отсутствие секрета в JSONL,
  сверяет кадр по точному числу байтов и отделяет искусственно заблокированный
  write от ожидания mutex вторым ответом. Это проверка измерительного инструмента,
  **не** end-to-end latency приложения.

Готовый прогон с relay и обеими трассировками анализируется офлайн:
`python3 r22/sdk-build/distribution.py r22/runs/combined-trace1`. В расчёт
входят только записи из одного worker PID и одной шкалы CLOCK_MONOTONIC;
проверяются operation, wire ID, точные байты ответа и порядок меток.
Отдельно выводятся приоритетные вызовы активной сессии до первого текста,
перекрытия с измеренными stdout holders, операции холодных архивов и размеры
страниц. P95 — ближайший ранг; вложенные sink times не складываются с
вмещающей стадией. Время sink/lock в этом стенде включает эффект relay,
плана выполнения потоков и backpressure читателя; без отдельного контроля
оно не является численной оценкой production latency.
