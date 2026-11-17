# Независимое ревью: однократное разрешение выбранного model alias

Проверены base `cdf4aa5` и candidate commit
`6a3eca9f7f8bca3969bd8da11c9b0c755a92405d`, source diff +1/−5,
`selected_model`, `to_model_config`, normalizer/binding functions, существующие
model/inline tests и исходные before/after logs. Reviewer не изменял checkout
и не запрашивал лишний повтор Rust tests.

**Вердикт: ACCEPT для этой ограниченной чистки. Блокирующих замечаний нет.**

- Проверка неизвестного alias остаётся в той же семантической точке: после
  нормализации локального каталога/selection, до вставки `active_provider`,
  сериализации providers, наследования и capture bindings. Старый
  `contains_key` и оставшийся `get().with_context()` сообщают одинаковое
  `unknown model alias {name:?}` для одного и того же отсутствующего ключа.
- `selected_model` возвращает owned `Option<ModelConfig>`; случай `None` не
  меняется. Раннее создание значения не заимствует mutable JSON object.
- Промежуточное наследование bindings лишь читает presets; capture меняет
  только `scope.components` и `scope.settings`, не `scope.presets` или
  `scope.selected`. Поэтому role default получает прежнее значение.
- На проверенных базах `ProviderProfileConfig::to_model_config` только
  клонирует поля и возвращает `Ok`. Перенос перед inheritance не переставляет
  обычные recoverable errors. Сигнатура `Result` намеренно сохранена; если
  conversion станет fallible, аргумент о порядке ошибок нужно пересмотреть.
- Существующие пять model и семь inline methods сохраняют success/error,
  nested/local/independent catalogue и explicit-route coverage. В исходных
  baseline и candidate logs совпадают все 12 имён: 12/12 PASS в каждом,
  без failures/skips. Это 12 уникальных методов и 24 executions, не full gate.

## Финальная проверка composed evidence

После завершения composed run отдельно прочитан `composed.log`: **15/15 PASS**,
0 failed/ignored, 771 filtered out. Список содержит те же 12 методов плюс три
существующих #171 cases: child shadowing, child-only alias и external-role
parent alias. Всего восемь model и семь inline методов. Это проверка результата
авторского запуска, не ещё один независимый запуск reviewer.

На composed #167/#171 source проверены тот же converter и те же границы
изменения binding state; patch применяется без конфликта. Process/security
callers, public signatures, contracts и workflows не меняются. Измеренного
ускорения нет; эти focused результаты не заявляются полным Core gate.
