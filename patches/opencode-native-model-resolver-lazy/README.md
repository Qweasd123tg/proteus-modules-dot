# R157 — OpenCode: отдельный ModelResolver только для resolve

Меняется один файл: `model/opencode-provider/runtime.mjs`. Патчи альтернативны:
`source.patch` для upstream Modules `9469e3b12529d08b1f4a76882693e2065e842c51`,
`composed.patch` после #452 → #462 → #465 → #466 → #467 → #468.
Не накладывать оба. Проверка `patch -p1 --fuzz=0` для каждой основы.

Model-only Worker не запрашивает отдельный entrypoint
`@opencode/core/dist/model-resolver.js` при initialize/describe/catalog или при
чтении env names. Первый resolve импортирует **тот же** закреплённый named
export, только после проверки model info / effort. Сигнал проверяется до
и после ожидания. Одновременные первые вызовы ждут одну загрузку, успешно
разобранная функция остаётся без нового import/await в повторном вызове;
ошибка не сохраняется отдельным rejected promise. Аргументы SDK, подготовка
seed, live catalog и прежняя native маршрутизация остаются прежними.

Первый валидный запрос может заплатить за отложенную загрузку. ESM import
сам по себе не прерывается, но отменённый вызов после ожидания не вызывает
resolver. Дефект файла/экспорта теперь обнаруживается при первом resolve
до inference, а не при загрузке metadata runtime. В смешанном Worker
другой slot (например workflow или compaction) может загрузить resolver
раньше. Проверка закреплённого upstream исходного графа не является
измерением emitted SDK: Bun может упаковать общий код в уже нужные chunks.
Нет утверждения, что весь native граф исчезает или что ускорился startup.

Проверены оба точных apply/reverse dry-run (0 fuzz, byte readback), Node
syntax и **8/8** Node VM тестов: фактические изменённые runtime и локальные
пакетные данные, инертные SDK/route. Сравнены metadata, отклонения model/
effort, холодный/повторный resolve с исходными args/signal, #465/#468
каталог, конкурирующие первые вызовы, отмена и битый либо отсутствующий
named export. Реальные npm SDK, процесс OpenCode, inference, сеть, память
и задержки не измерялись.
