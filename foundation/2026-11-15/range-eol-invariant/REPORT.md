# Ranged read: точные межстрочные разделители

## Итог

Подготовлен source-only candidate для уже известной части P2 из tools-integration: non-numbered read_file(range) нормализует CRLF, после чего точный многострочный old_string не находится в edit_file. Это не новая finding и не новый runtime reproduction. PR116 исправляет другую сторону исходного отчёта, direct_patch; PR119 отдельно задаёт общий UTF-8 decoder.

Выбран узкий инвариант без нового framework: **обычный ranged output сохраняет реальные разделители между выбранными строками**. Удаление terminator последней выбранной строки остаётся прежним. Numbered output остаётся display-представлением с LF. Поэтому не заявляется полная побайтовая эквивалентность всех выбранных строк или гарантия любого последующего edit.

Независимый exact source review не нашёл blockers у standalone candidate. Проверка rebase и финального отчёта отражается в RANGE-EOL-INDEPENDENT-REVIEW.md. Все пять тестов только предложены, NOT RUN; Rust/toolchain/приложение не запускались.

## Версии и evidence

- Modules: c035142558f0fca43e9772fc0e50ca293abf1531.
- Core main: bcbda4435534a296c707a1daa250813d692f68e1.
- Actual Modules Core dependency: 41bdfffa6e70228278b4abc758b7f81a12672f35.
- Delivery main при начале: 988935d093edcd5e9116e00c9ff90296e8bf528b, включая PR123 LSP HOLD.

Повторная проверка в the final source-ref check подтверждает те же три main SHA.

SOURCES.json и VERIFICATION.json содержат 12 exact Git blobs. Релевантный Core ok_result прочитан на actual pin: он передаёт output в JSON без newline normalization. Полные source snapshots не публикуются; это не утверждение полного review каждого исходного файла.

Исторический отчёт tools-integration относится к Modules3270dc0/Core pinb5fac842. Его прежний mock/tool-level запуск не проверяет новый patch. PR123 остаётся HOLD, как и другие ранее открытые границы; данный patch их не закрывает.

## Изменение общей причины

До patch render_range удаляет LF и предшествующий CR с каждой строки, затем добавляет синтетический LF перед каждой следующей строкой. Даже не-numbered режим становится преобразованным display-текстом. В full read и обычном read_many содержимое сохраняется, поэтому результат зависит от способа чтения.

Candidate переносит в следующую итерацию маленький borrowed delimiter:
1. Существующий strip распознаёт LF, CRLF или отсутствие terminator; bare CR остаётся содержимым.
2. После принятия выбранной строки её EOL становится разделителем следующей выбранной строки. Пропущенный prefix не создаёт leading separator.
3. Разделитель выводится только при принятии следующей строки. Последний EOL по-прежнему не выводится.
4. Бюджет учитывает separator.len(), то есть оба байта CRLF; переносимый межстрочный разделитель не делится ради бюджета.
5. В numbered режиме переносится прежний LF, не сырой EOL.
6. Tool description явно сообщает разницу non-numbered и numbered projection.

Это устраняет семейство LF/CRLF/mixed inter-line conversion, не нормализуя весь файл и не добавляя ещё один parser/API/DTO. Production read.rs: 311→317 строк до первого cfg(test), +6 строк. Это не оптимизация LOC или измеренная экономия runtime.

Пример:
- Файл: `old\r\nkeep\r\n`.
- Прежний unnumbered range: `old\nkeep`.
- Candidate: `old\r\nkeep`, точный contiguous substring исходника.
- Full read остаётся `old\r\nkeep\r\n`.
- Numbered range остаётся `1\told\n2\tkeep`.

## Точные границы гарантии

- Сохраняются **межстрочные** bytes, а не terminator последней выбранной строки. Empty output не становится допустимым edit preimage.
- edit_file остаётся literal: old_string должен быть непустым и уникальным, если replace_all=false. new_string вставляется буквально. Patch не конвертирует EOL replacement и не делает нечёткий поиск.
- Tool-level round-trip fixture использует неизменённый файл, уникальный snippet и replacement, сохраняющий его EOL. Это не транзакционная гарантия против внешнего редактора, не multi-agent guarantee и не проверка model/hook/provider представления.
- Numbered и batch-header output не являются напрямую old_string целого файла. В batch controls сравнивается только прежнее представление, production read_many не меняется.
- Scan/read/output limits и EOF eligibility не меняются. При сохранённом CRLF под тем же byte limit может поместиться меньше body bytes/строк, чем в прежнем нормализованном output.
- available==0 по-прежнему отвергает следующую строку, даже пустую; этот admission contract не расширяется.
- UTF-8 prefix truncation может принять нулевое число body bytes последней попытки строки. returned_lines не доказывает полноту/непустоту каждой строки.
- Атомарно добавляется только уже распознанный переносимый межстрочный separator. Не заявляется новый atomic-CRLF contract для необследованной raw scan boundary, которая могла оборвать строку перед ещё не прочитанным LF.
- Line-limit не делает дополнительное чтение для определения EOF; total_lines остаётся unknown, где был unknown.
- Full read, write/edit implementation, path resolution, authority и coordination не меняются. Security/flagged направления не исследовались.

## Пять предложенных тестов, NOT RUN

Четыре внутренних теста:
- LF/CRLF/mixed, start_line>1, blank lines, bare CR, CRCRLF, empty/out-of-range, отсутствие последнего EOL.
- Numbered LF controls и прежняя conservative line-limit metadata.
- Двухбайтовый CRLF в output budget, точное помещение UTF-8 body, один/два оставшихся байта без body capacity.
- Raw scanned_bytes, observed EOF, start/end/returned_lines при CRLF.

Один ToolModule-style тест:
- Реальные read_file → edit_file вызовы в предлагаемых LF/CRLF/mixed fixtures.
- Full read и read_many controls.
- Normalized old_string negative control сохраняет прежний exact-match отказ.
- Использование возвращённого exact snippet меняет только old→new, сохраняя остальное содержимое.

Здесь «вызовы» описывают код предлагаемых тестов, не выполненный прогон. Existing budget/UTF-8 tests также не запускались. Нужен разрешённый focused file-tools gate на выбранном exact patch; предлагаемая команда при доступном toolchain: python3 scripts/test.py -p file-tools --lib. Никакая команда проекта этим аудитом не запускалась.

## Текстовая композиция, не интеграционная проверка

- range-eol.patch применяется к исходному c0351425. git apply --check --whitespace=error и сравнение applied/after bytes выполнены.
- Оригиналы range-eol.patch и PR119 НЕ применяются последовательно без разрешения контекста: read.rs и tests.rs конфликтуют. Не считать их автоматически stackable.
- range-eol-on-PR119.patch предназначен **после** bounded-read-utf8.patch из PR119. Он сохраняет shared decode_read_bytes, прежнее условие budget/complete и обе test modules.
- Три расположения PR116 относительно этого ordered pair применены текстово; итоговые деревья побайтово одинаковы. PR116 не меняет file-tools paths.
- VERIFICATION.json сохраняет и неудачные checks оригинальных patches, и удачные rebased orders. Это не compile/build/test/runtime evidence.

## Артефакты

- Standalone patch SHA256: 0ce98894a787547953f819cb43b5e12a6834bdd66f7e7c1ee0e008e33eecf27d.
- Rebased-on-PR119 patch SHA256: c9afa29286e6a149f2f0439eed207d6b2b2f579ba1c926e1703a39b1e5000fc8.
- Exact source identities и independent review; полные исходники и рабочие копии не включены.
- VERIFICATION.json, MEASUREMENTS.json и SOURCES.json.

Ничего не устанавливалось, не компилировалось и не запускалось из проекта. Production/upstream refs не изменялись, на момент подготовки публикаций не было. Готов только непроверенный source candidate, не подтверждённый production fix.
