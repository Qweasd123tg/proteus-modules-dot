# Core: один перенос готовых params в исходящий JSON-RPC request

**База**: Proteus-core `048378da7cbe890d8bf8a0152e55eb28ecb5013d`. Самостоятельный `source.patch` включает production-код и два regression-теста: SHA-256 `b3a7280c5cc3baef0f2ae123e01c2238556f83c6e5a10b1279213529548be5b6`.

## Что меняется

Оба caller'а приватного `wire::request` уже вызывают `serde_json::to_value` для канонического DTO: `initialize_transport` для initialize и `invocation_request` для `ProcessComponentInvocation`. Старое `json!({"params": params, ...})` повторно обходит и выделяет всё дерево. Новая версия строит те же три поля envelope и последним вставляет готовое четвёртое поле `params` по владению. Порядок вставки сохраняется и при `preserve_order`.

Первое преобразование DTO **оставлено**: сверхрезервированный буфер из пользовательского `Value` не переезжает в очередь writer. Приём, проверка DTO, маршрутизация, ожидание, подсчёт фактического размера frame и byte/count limits writer не менялись. Никаких новых правил декодирования или форматов. На callback, notification и ответ изменение не распространяется.

## Результаты

Счётчик single-threaded Rust allocator вокруг **реального** `invocation_request`; за пределами замера: построение и проверка typed `WriteCache`, запись контрольного JSON, процессы и доставка. Счётчик вызовов суммирует alloc/alloc_zeroed/realloc, а байты означают сумму размеров этих запросов, не RSS и не пик.

| Валидный WriteCache, root | Режим serde_json | Wire (без перевода строки) | Вызовы stock → candidate | Байты stock → candidate |
|---|---|---:|---:|---:|
| 4 096 вложенных строк | default | 211 352 | 49 249 → 24 630 | 6 368 581 → 3 184 638 |
| 4 096 вложенных строк | preserve_order | 211 352 | 57 460 → 28 737 | 5 480 041 → 2 740 642 |
| Строка в 1 МиБ | default | 1 049 157 | 97 → 54 | 2 108 741 → 1 054 718 |
| Строка в 1 МиБ | preserve_order | 1 049 157 | 116 → 65 | 2 104 937 → 1 053 090 |

21/21 точных побайтных сравнений в **каждом** режиме: десять форм payload × root и nested, плюс initialize-envelope; среди контролей Unicode и экранирование, сознательно несортированные ключи, уже разобранный объект с повторяющимся ключом, JSON null и числа предельных значений. Тесты не утверждают одинаковый порядок между режимами, только внутри пары до/после. Результаты/хеши по обоим режимам в соседних папках.

Тесты crate: 55 unit + 21 интеграционный broker + 1 startup deadline успешно для каждого из default и preserve_order. Среди них: unknown/ambiguous envelope, outbound frame cap, очереди/отмена, targeted cancel, сбой worker и timeout. Новые тесты смотрят на байты/перенос именно вложенного String и отдельно на отбрасывание большого резерва capacity у исходной короткой строки. На stock новый тест переноса падает, а тест сохранения исходной нормализации проходит. Проверены формат изменённого файла и применимость патча к чистому индексу базы.

**Границы:** нет замера ACK/latency, RSS, записи SQLite/диска, GPU или всей сессии. Синтетический вызов существующего wire builder с валидным storage DTO не означает измеренного ускорения приложения. Повторное преобразование *входного* DTO в Value оставлено.

## Повтор

Rust 1.95.0, Cargo.lock из базы; Linux + lld, GNU patch, bash, python3, sha256sum. Из отдельной рабочей копии Core на базе:

```sh
PACKET=/absolute/path/to/this/packet
git apply --check "$PACKET/source.patch"
git apply "$PACKET/source.patch"
for mode in default preserve_order; do
  flags=()
  test "$mode" = default || flags=(--features serde_json/preserve_order)
  cargo test --locked -p proteus-module-protocol "${flags[@]}"
  cargo test --locked -p proteus-module-protocol --no-run --message-format=json "${flags[@]}" > "/tmp/wire-$mode.artifacts.jsonl"
  bash "$PACKET/reproduce.sh" "$PWD" "/tmp/wire-$mode.artifacts.jsonl" "/tmp/wire-r35-$mode"
done
```

Измеритель компилирует исходный wire.rs непосредственно из указанного git commit и его копию с тем же патчем, связывая обе с одинаковыми Cargo-зависимостями соответствующего режима. `diff -qr` проверяет полные байты, после чего сохраняются SHA-256 и CSV. Компиляция source-пробы с `opt-level=3`, размеры и числа запросов не выдаются за CPU-тайминги.
