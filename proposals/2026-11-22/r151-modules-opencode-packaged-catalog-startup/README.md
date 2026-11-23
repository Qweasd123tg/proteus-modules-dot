# R151 — OpenCode: первый describe из локального каталога

Оба патча нужны. К точному Modules `9469e3b12529d08b1f4a76882693e2065e842c51`
применить `source.patch` и `assets.patch` с `-p1 --fuzz=0`. Они также независимо
накладываются после draft #462 (head `1f8334ff24f59fcefadcba4ac8ce341e031b9c60`);
#462 меняет только Worker entrypoint и не входит в этот патч.

Для Go и Zen без явного источника: точный поддерживаемый chat ID из поставки
получает describe, resolve и нужные имена env для credential reading из одних
и тех же проверенных данных. Выбор не зависит от порядка RPC. Обычное обновление
Worker без замены пакета использует те же данные. Ошибка целостности seed не
переводит уже принятое описание на другой источник. Новый/неподходящий ID
проходит старую независимую ветку. Пользовательские `models_file` и `models_url`
не меняются. Первый describe покрытого ID не запускает HTTP; это не относится
к восстановлению сохранённого выбора, picker, quota и всему старту Desktop.

Picker продолжает старая ветка discovery: прежние состав, порядок, hidden
и label; для живых совпадающих seed IDs заменяются только доступные варианты
и default reasoning effort, чтобы они совпали с resolve. Удалённая из live
каталога модель не добавляется обратно в picker: setters Core сохраняют
прежнее требование membership. Уже настроенная seed-модель может запускаться
по закреплённым данным, хотя явно выбрать удалённый ID в picker всё ещё нельзя.
Нет постоянного last-good, фонового обновления или нового Core протокола.
Локальный snapshot и прежний TTL snapshot, когда обе ветки вызывались, имеют
отдельные прежние лимиты на snapshot; абсолютная память не измерялась.

Два seed-файла из исходного OpenCode `527f0b931d1f9b3ebd34e106c51b31ce5db5b075`
соответствуют raw bundled snapshot точного npm `@opencode/core@2.0.22`:
Git blob `a177c5468699a3ce48b27bc417847a0804af1564`, SHA-256
`9c9188aba5c3a6c7e30d9751fa6f1fcdb8d142710695f8ca434c4e5d8c8da3ce`.
Go 22 380 B `7a87809e9992b264e3649cb3573a96231d95bff98293817869338c12792f8cf3`;
Zen 75 647 B `17262a403753acb2d5899721ba2007c888b49d2c16ac4a70aa328c689818db62`.
Provenance и лицензия дополнены в NOTICE. Достоверные bytes из одного
ограниченного fd передаются в scoped FSUtil и затем в штатный ModelsDev
normalize; повторного открытия файла нет.

Проверено: обе основы, forward + reverse dry-run 0 fuzz и readback;
Node syntax; 5 из 5 узких тестов с **реальным** изменённым runtime/adapter,
проверкой реальных seed файлов и **инертным** SDK/inference/auth;
изолированный прогон копирования **реальным** installer main с заглушёнными npm
и manifest helper. Настоящий npm/SDK v14, полный broker/Core/Desktop, сетевой
каталог, benchmark, PSS и время не запускались. Два repo-native
`tests/packaged-catalog.test.mjs` подготовлены, но не выполнены без vendor tree.

При допуске установить в новый физический prefix, запустить новый Core и не
переименовывать/заменять путь, к которому всё ещё привязан старый Core.
Обычный in-place install или изменение symlink/stable ready path на живом Core
не гарантирует неизменную связку Worker/пакет на respawn. Автоматическая
portable-упаковка OpenCode не подтверждена этими тестами.
