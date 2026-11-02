# Финальный ответ без лишних глубоких копий

Source-патч для Proteus-modules `e9c4e1f78a053b91d77a70ea145e2ae873da51cf`.
Изменён только `model/model-pack/src/adapters/openai/stream.rs`.

`finalize_completed_event` уже получает JSON по владению. Вместо копирования
вложенного `response`, массива `output` и восстановленных streamed items патч
перемещает их через `Value::take`, `std::mem::take` и consuming iteration.
Заимствованный `fallback_items` по-прежнему копируется: состояние потока
сохраняется для повторного terminal event. Новый кэш, настройка или API не нужны.

Сохраняются выбор вложенного response при его наличии (включая null), прямой
response без обёртки, замена отсутствующего/не-массива output, первый элемент
с совпадающим ID, порядок добавления, metadata и приоритет ошибок. Closure
восстановления вызывается в прежней ветке и один раз. Остальная трансляция
событий, включая отдельный borrowed путь, не меняется.

Существующие тесты `stream/tests.rs` уже описывают lazy reconstruction,
malformed output, duplicate IDs, metadata/error precedence и повторное
завершение потока. Они оставлены без изменений; отдельная тестовая матрица
или инфраструктура не добавлена.

## Проверено

- Точный исходный Git blob и SHA256 до/после.
- Strict apply/reverse с `--whitespace=error` и побайтовым восстановлением.
- Прямой установленный rustfmt 1.95.0, edition 2024, `skip_children=true`.
- Прочитаны вызов с owned JSON и существующие regression tests.

**Тесты, Cargo, сборка, CI и приложение не запускались.** Убраны конкретные
копирования по исходникам; численный выигрыш скорости или RAM не измерен.
После переноса нужен целевой тестовый scope model-pack. Runtime-проверки и
сборка пакета выполняются по upstream README/AGENTS, без пересборки остальных
пакетов ради этой правки.

Применять `owned-completed-response.patch` к указанной ревизии Modules.
Исходный репозиторий и dependency pins этим пакетом автоматически не меняются.
