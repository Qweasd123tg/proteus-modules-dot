# Proteus Git: две новые границы сохранности amend-message

Проверено 2026-11-13. Это **не повтор** потери незавершённого поля при A→B→A, Input echo race или устаревшего action, попавшего в другую session. Здесь одна живая session, FIFO action sequence и успешно принятый draft. Ошибка возникает между подготовкой amend и выполнением git commit.

## Итог

1. **P2: временная ошибка чтения полного commit message приводит к успешному amend только с заголовком.** Body и trailers исчезают из нового HEAD без предупреждения о неполной загрузке.
2. **P2: amend не привязан к HEAD, для которого его включили.** После checkout другой ветки или нового коммита в той же ветке старое сообщение отправляется как amend для уже другого HEAD.

Оба результата подтверждены не только fixture-ответами: неизменённый Git+SDK отправляет запрос в **настоящий Core HTTP**, который изменяет только специально созданный локальный Git repository. Состояние проверено независимым `git log -1 --format=%B` после POST200. Ни remote, ни пользовательские репозитории, ни провайдер/модель в опыте не участвуют. Native GPUI кликами не проверялся.

**Граница ущерба:** amend выполняется только после последующего пользовательского действия Commit/Amend; он не происходит автоматически от ошибки чтения или checkout. В возвращённом UI-дереве редактор и кнопка Amend видимы, но предупреждения о неполном сообщении или смене цели нет. Старые commit objects после опытов по-прежнему читаются, поэтому это не доказательство безвозвратной потери: возможно восстановление через Git/reflog. Содержимое файлов в этих опытах не потеряно.

## Зафиксированные версии

Повторно сверены `git ls-remote origin HEAD`:

- Extensions: `4df3d0f7c168aa2947a5b014cf02f92984499d3f`.
- Core: `89997df995df7c39b713e16aba216ecb19c8f497`.
- Desktop: `75bf201764278eac4b50d156650edcf1429101ff` (только источник UI-маршрута).

Git binary собран из чистого `git archive HEAD`, отдельный Cargo target. Core binary совпадает SHA-256 с ранее зафиксированной сборкой этого HEAD. Полная provenance и хеши в `source-provenance.json`. Production не патчился; ничего не публиковалось.

## 1. Неполный prefill после ошибки чтения

### Воспроизведение

1. HEAD имеет сообщение:
   ```text
   Alpha change

   Important Alpha explanation.

   Refs: ALPHA-123
   ```
2. Поле commit message пустое. Включается **Amend Commit**.
3. Только GET `/workspace/commit?hash=…` получает искусственный однократный HTTP503. Остальные запросы обслуживает настоящий Core.
4. Git показывает `Alpha change`, оставляет Amend включённым, кнопку доступной и не показывает error. Обычный Refresh после восстановления HTTP не догружает полный текст.
5. Нажатие Commit отправляет `{message:"Alpha change", amend:true, …}`.
6. Core отвечает 200; реальный новый HEAD содержит **только `Alpha change`**. Поле редактора очищается как после обычного успеха.

Это lossy fallback, а не обработка неудачного commit: сам commit успешен. В отдельном контроле, если именно POST commit завершается ошибкой, прежний полный draft и amend-флаг сохраняются.

### Причина

- [`toggle_amend`, main.rs:446–467](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L446-L467): ошибка `commit_details` подавляется через `unwrap_or_else`, подставляется только `head.summary`. Это значение записывается в `message` и `amend_message` как полноценный успешный prefill; ошибка не записывается в UI state.
- [`commit`, main.rs:470–487](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L470-L487): отсутствует признак incomplete prefill; непустого summary достаточно для запроса.
- [Core write.rs:106–134](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/http/workspace/git/write.rs#L106-L134): применяется обычное `git commit -m <message> --amend`, без `--no-edit`, следовательно переданный summary заменяет всё сообщение.

### Контроли

- Успешное чтение: summary+body+Refs сохраняются полностью.
- Заранее набранный непустой пользовательский draft: сохраняется, запрос prefill вообще не делается.
- Ошибка POST commit: полный draft остаётся, amend не сбрасывается.
- Ошибка GET prefill + последующий обычный Refresh: body не восстанавливается.

## 2. Старый amend применяется к новому HEAD

### Воспроизведение A: явный checkout

1. На `main`, HEAD Alpha, включается Amend. Поле получает полное Alpha-message.
2. Через обычный Git action выполняется checkout `beta`; Core возвращает HEAD Beta.
3. Новая ветка и HEAD уже отражены в статусе, но поле всё ещё содержит Alpha-message, а Amend включён и доступен.
4. Commit отправляет Alpha-message с `amend:true`; реальный HEAD ветки `beta` получает Alpha-message вместо собственного Beta-message.

### Воспроизведение B: новая фиксация в той же ветке

1. На `main` включается Amend для Alpha.
2. Отдельный локальный тестовый Git actor создаёт новый **non-empty** commit Beta в `main`.
3. Обычный Refresh доставляет новый HEAD в расширение. Повторного включения Amend нет.
4. Следующий Commit успешно переписывает **Beta** сообщением **Alpha**. Ветка при этом вообще не менялась.

Здесь нет гонки между последним GET и POST: смена HEAD уже успешно обработана до отправки commit. Пятисекундный poll или событие run_settled также ведут через тот же `update()`, но именно эти способы обновления в данном опыте отдельно не воспроизводились.

### Причина

- [checkout, main.rs:277–295](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L277-L295) обновляет changes, но не amend intent.
- [`update`, main.rs:385–407](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/main.rs#L385-L407) распознаёт смену `(branch, HEAD.short, refs_revision)`, однако инвалидирует только каталоги/кэши. `amend`, `amend_message`, `message` остаются без связи с целью.
- [UI panel.rs:443–493](https://github.com/Proteus-harness/Proteus-desktop-extensions/blob/4df3d0f7c168aa2947a5b014cf02f92984499d3f/packages/git/src/panel.rs#L443-L493) использует сохранённый bool для enabled Amend; action не несёт ожидаемый HEAD.
- [Core CommitRequest:41–47](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/crates/proteus-core/src/app_server/http/workspace/requests.rs#L41-L47) тоже не содержит expected HEAD. Core корректно выполняет полученный `--amend` для текущего HEAD, не зная, для какого коммита редактор подготовил текст.

### Контроли и исключения

- После checkout вручную выключить и снова включить Amend: подставляется Beta-message, следующая операция корректна.
- Обычный непустой draft без Amend переживает checkout и отправляется как новый commit, не как amend. Исправление не должно стирать такие drafts.
- Если новый HEAD был создан как **empty commit**, Git отказал последующему amend с HTTP400, поскольку запрос не содержит `--allow-empty`; исходный Beta-message сохранился. Этот вариант не даёт успешной перезаписи. Контроль сохранён в `empty-commit-control.json` и `actual-core-repeat.log`. Затем опыт повторён с обычным изменяющим файл commit и дал POST200/подмену message.

## Проверки и evidence

- Чистая сборка Git: PASS.
- Штатные тесты: **Git 35 + SDK 51 passed**, doc tests 0.
- `repro.py`: **8/8 wire-сценариев** соответствуют наблюдениям; неизменённый production Git+SDK, синтетическая API.
- `repro_core.py`: **4/4 end-to-end сценария** на настоящем Core и отдельных Git repositories: healthy, failed details, checkout, same-branch non-empty HEAD change.
- Первые три actual-Core сценария повторены успешно в трёх независимых наборах fixtures.
- Два новых desired-safety regression tests: **ожидаемо красные**, exit101 (`regressions-red.log`, `regressions.patch`). Это test-only patch, не production fix; после прогона исходный tests.rs восстановлен.
- `--require-fixed` для wire-контракта: ожидаемо красный, exit1.
- Не запускались: native Desktop, release packaging, full Core suite, remote push, real provider. Не проверены все сочетания hooks/conflicts/signoff и одновременное изменение HEAD непосредственно между последней проверкой и commit.

Основная фактическая трасса: `core-run-1794585904986221378/results.json` и четыре `*/trace.json`; логи `actual-core-final.log`, `observed.log`, `baseline.log`. В архиве нет binaries, Cargo target, `.git` и runtime session stores. Скрипты создают новые изолированные fixtures для повторения.

## Направление исправления

1. Не превращать ошибку чтения полного message в успешный partial draft. Сохранить существующий текст, показать retry/error и не разрешать незаметный amend неполным автоподставленным текстом. Явно введённое пользователем сообщение не должно блокироваться как ошибочная загрузка, которой не было.
2. Отделить пользовательский draft от amend intent. При включении Amend сохранить **полный target hash**. После смены HEAD/ветки отменить или заблокировать старый amend до явного повторного выбора, сохранив введённый текст для восстановления/копирования.
3. Для защиты и от настоящей межпроцессной гонки нужен server-side expected-HEAD контракт и согласованное выполнение mutation; одной проверки bool в UI недостаточно. Это шире двух воспроизведённых случаев и требует отдельной проверки.

Не следует «лечить» второй дефект безусловным `message.clear()` на каждом обновлении refs: так появится новая потеря корректного пользовательского draft.
