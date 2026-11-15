# Portable Desktop/Extensions compatibility

Исправление известной D2-02: итоговый bundle проверяет protocol и
required_features расширений перед заменой установленной папки.

- [Отчёт и ограничения](REPORT.md)
- [Независимая проверка](REVIEW.md)
- [Standalone patch](portable-compatibility.patch)
- [Альтернатива после #142](portable-compatibility-on-PR142.patch)
- [Исходники](SOURCES.json), [результаты](VERIFICATION.json)

На точном Desktop `7eaf70c67dabba8595d98029c875ffc3f59209ad` выберите только один
patch-вариант. Второй требует сначала опубликованный #142 и адаптирует его
синтетический test harness. Не применяйте оба варианта.

После применения:

```sh
python3 -I -B -S scripts/test_release_portable_compatibility.py -v
# Только для варианта после #142:
python3 -I -B -S scripts/test_portable_serialization.py -v
```

12 новых методов PASS; на combined #142 также 6 адаптированных PASS.
Baseline: четыре ожидаемых assertion failures. Это синтетические
Python/filesystem проверки, не реальная сборка или runtime qualification.
Upstream, dependency pins и пользовательская установка не менялись.
