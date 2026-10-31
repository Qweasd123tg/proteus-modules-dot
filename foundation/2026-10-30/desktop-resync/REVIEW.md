# Независимое source review

Автор исследования очереди и config repair независимо проверил settlement
repair; автор settlement repair независимо проверил config repair. Затем
владелец общей задачи рассмотрел обе границы. Блокирующих замечаний в узком
source scope не осталось. Это не успешный behavioral gate.

## Settlement

Core events.rs на lag выдаёт EventStreamLagged, затем актуальный snapshot и
пропускает события до watermark. runs.rs завершает durable/runtime работу,
получает completed transcript и под admission lock публикует terminal state и
snapshot. Desktop раньше обновлял execution из snapshot без RunSettled;
chats.rs использует этот сигнал для summaries/HostEvent, поэтому
SessionStateChanged не эквивалентен ему.

Сохранённая snapshot_identity — session + stream уже принятого baseline;
она переживает reset курсора подключения, но не делает чужую generation
прежней. Проверяются известный active id, совпадающий terminal last id,
отсутствие нового active. После apply_snapshot old active исчезает, поэтому
повтор не выдаёт сигнал. Сигнал следует за применением snapshot. Existing
context refresh snapshot сохранён. Root очищается при settlement и не является
идентичностью app run: требование равенства root было бы ошибкой.

Исходники пяти tests покрывают Success/Error/Canceled/Timeout, повтор,
reconnect той же generation, restart, смену/очистку root, неизвестную историю,
иной id, следующий active, nonterminal last, rejected stale/foreign/equal
snapshot, ранее доставленный terminal ExecutionUpdated и чужой session id.
Они проверяют production decision helper и ordering через Session/History,
но не реальную доставку subscriber GPUI. Не выводится завершение каждого
пропущенного run: `last` хранит только последний.

## Config

У единственного producer каждый реальный reconnect следует после успешно
отправленного Disconnected; неудачная отправка завершает поток. FIFO apply
записывает link_error=Some, затем Connected считывает его до очистки. Поэтому
существующее поле отличает reconnect от первого подключения без нового флага.
Shutdown не reconnect; rehost сохраняет task. Initial Chat::new load_config
не удалён, в том числе для offline initialization.

EventStreamLagged принимается cursor независимо от root; это transport
resync, в том числе activity overflow. Существующий config endpoint можно
прочитать без ожидания replacement transcript. Activity-only lag может
вызвать лишний refresh: DTO не указывает источник lag. Несколько lag могут
запустить несколько запросов; нового coalescing или cache нет.

load_config увеличивает generation до local request. Устаревший local success
не применяется и не запускает discovery. apply_config увеличивает generation;
discovery запоминает новую и применяется только при совпадении. Новый reload
или settings apply инвалидирует старые ответы обоих этапов. Это порядок
client requests, не server revision protocol. Существующие stale error notices
в общем Chat::call не подавлены; их поведение не расширялось этим патчем.

## Очередь / восстановление

last receiver drop в async-channel 2.5.0 закрывает канал и будит blocked send;
receiver-drop не является причиной HOLD. Dedicated thread не блокирует UI
executor. Но retained receiver без draining задерживает чтение heartbeat,
Shutdown и disconnect, а upstream broadcast продолжает публикацию. Snapshot
сохраняет transcript/execution, отдельный watch — pending/queued state, но не
полный журнал notifications. Generic Error и reload failure не восстанавливаются.
Shutdown имеет исключение watermark для сохранившегося события; не заявляется
доказанная потеря обычного финального Shutdown без соответствующего producer
schedule. Состояние journal не повреждается медленным observer.

## Статическая проверка

Исправлена лишняя завершающая пустая строка в локальной копии исходного
snapshot_tests.rs: точный preimage blob теперь
`186d3dcd4130a1b7c132e36118a26abfc42af2f3`. Патч строится от точных байтов,
не от изменённой локальной копии. Чужие held action-route изменения не включены.
Проверены отдельные патчи, общий результат, оба порядка с PR69 и обратное
восстановление. Никакого внешнего изменения репозиториев этим пакетом не сделано.
