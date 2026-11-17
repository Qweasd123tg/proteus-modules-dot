# Буквальное значение компактного поля

Нужны Python 3, rustc, исходный Desktop `2307e9c67125bbe66f15ced51317a2dfcc437aa4`, Core `c2cbadee518788f306ffb2b5271036b2658ea8cc`, копия Desktop после применения патча и набор уже скомпилированных совместимых rlib для serde с derive и serde_json. Полный Core/Desktop не запускается. В стенд из исходников берутся используемые типы схемы Core и формат/разбор поля Desktop. Сами UI, сохранение настроек и сторонние расширения не запускаются.

Из каталога пакета: `python3 checks/compact/replay.py --core /path/to/Core --desktop /path/to/Desktop --candidate /path/to/patched-Desktop --deps /path/to/deps`. Если в каталоге несколько вариантов, укажите также `--serde /path/to/libserde-….rlib --serde-json /path/to/libserde_json-….rlib`. Rustc можно задать флагом `--rustc`. [Сохранённый протокол](structural.log). Смена представления входного текста отделена от ручного ввода новых значений.
