# Потоковая упаковка ZIP расширений

Source-only patch для `Proteus-harness/Proteus-desktop-extensions`
`bb0ecdc11bed1951d99e557e49f12652a173e9dd`.

## Изменение

В обоих ZIP-режимах `package.py` заменено чтение всего файла в Python `bytes`
на стандартный `ZipFile.write`. Так устраняется явная allocation размером с
каждое вложение, включая бинарник. Cargo, выбор компонентов, release-профиль,
оптимизации, pins и lockfiles не меняются. Измеренного выигрыша RSS или времени
не заявлено.

Файлы по-прежнему берутся из уже подготовленной отдельной staging-папки.
Сохраняются порядок/имена вложений, timestamps, права исполнения, DEFLATE,
default compression level и следование лицензионным symlink при копировании.
Выбранный ZIP по-прежнему проверяется через `testzip()` и публикуется через
`os.replace`: ошибка сохраняет прежний архив. Полный набор сохраняет прежнюю
неатомарную публикацию; новая гарантия rollback для него не заявляется.

`ZipFile.write` использует тот же `ZipInfo.from_file`, что прежний код.
Проверены [CPython 3.8.20](https://github.com/python/cpython/blob/v3.8.20/Lib/zipfile.py)
и [3.12.15](https://github.com/python/cpython/blob/v3.12.15/Lib/zipfile/__init__.py):
стандартная реализация передаёт содержимое частями, не целым `bytes`.
README репозитория требует Python 3 без minor-версии, CI закрепляет 3.12.15.
Новый API не повышает существующий version floor: уже используемый
`Path.unlink(missing_ok=True)` появился в Python 3.8.

ZIP64 остаётся включён по умолчанию. Старый writer задавал размер через
`len(bytes)`, новый получает его через `stat` до чтения. Для стабильных файлов
частной staging-папки это одинаковый размер и тот же ZIP64 threshold. Patch
не добавляет принудительные ZIP64 headers или новый механизм блокировки файлов.

## Regression sources

Изменён существующий `tests/test_package_selection.py`:

- оба ZIP-режима сравниваются с прежним writer по payload и metadata;
- проверяются executable mode, Unicode/nested/empty assets и license symlink;
- во время упаковки запрещён вызов `Path.read_bytes`;
- ZIP64 проверяется маленьким настоящим файлом с уменьшенным test threshold;
- failure-injection существующего rollback-теста перенесён на реальный `write`.

Добавлена краткая запись в существующий README репозитория.

## Статус проверки

Git blob identities, SHA256, Python AST, strict whitespace/application checks
и byte-identical reconstruction проверены. Независимый source review не
выявил конкретного blocker. **Tests/builds/Cargo/CI/runtime/benchmarks не
запускались.** Source review и синтаксический разбор не заменяют выполнение.

После применения patch на указанную base, на разрешённом executor:

```sh
python3 -m unittest discover -s tests -p 'test_package_selection.py'
```

Первый целевой gate — CI-pinned Python 3.12.15. Не заменяйте имя теста общим
`test_*.py` ради этой правки: `test_bundle.py` запускает Cargo и процессы
расширений. Штатные executable release gates остаются отдельной проверкой.

[SOURCES.json](SOURCES.json) закрепляет исходники;
[VALIDATION.json](VALIDATION.json) — выполненные статические проверки;
[SHA256SUMS](SHA256SUMS) — контрольные суммы.
Patch применяется в checkout Extensions, не в delivery-репозитории.
Upstream не изменён; source review не подтверждает прохождение upstream release gates.
