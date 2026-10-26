# Strict JSON: реальный AgentRuntime и официальный reader

Экспериментальный проверочный пакет; успешный runtime здесь пока не заявлен.
Хост использует Core3f (`3f36a003b4f3fde2242fc80f7aedac00dd127d1d`), а
неизменённый официальный executable — Modules7f
(`7fceaebc3bed8add9b0e3091110f59deca86ba46`) с собственным SDKbee0.
Strict producer/hook взяты из PR4, commit
`056c8ded32f36352ca846d4b3ce807359e32db38`. Три target-графа не объединяются.
Совместимость процессного протокола должна проверяться, а не предполагаться.

CI сначала требует пять реальных Linux-проверок управления дочерними
процессами, включая отдельную process group и orphan adoption. Затем —
16 Rust-тестов авторского model/policy fixture и сборка ровно указанных бинарников.
Отдельный matching diagnostic сохраняется перед полным свежим набором:
matching, wrong_suite, wrong_config, missing_assertion, omitted, read_denied,
approval_denied и default_deny. Последний — direct BoundTools, **не turn**.
Семь turns проверяют настоящее создание/чтение файла, точный Ask/approval,
strict receipt, canonical history, сохранённый journal и завершение процесса.

47 синтетических validator controls, девять controller mocks и 35 envelope
controls остаются отдельными слоями и не заменяют реальный runtime.
Пять live controls обязательны на каждом runner перед Cargo и Core.
Никакой сетевой sandbox, production model или произвольная сборка не заявлены.

Workflow: `.github/workflows/check-strict-fullturn.yml`. Дедлайн supervisor —
45 минут; начальный запас — 8 GiB; sampled stop — 1 GiB + 128 MiB, без очистки.
Артефакты ограничены 32 MiB и 512 entries, логи — 8 MiB на файл.
После ошибки runtime прекращается; dedicated job завершается после bounded
snapshot/upload. Внешний supervisor сам по себе не доказывает cleanup дерева.
Перед принятием нужны точный CI head, все восемь semantic cases, process receipts
и независимая сверка сохранённого tar-инвентаря. Исторический зелёный PR4 не
является доказательством этого нового набора.
