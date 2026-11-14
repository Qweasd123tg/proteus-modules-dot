# Дополнительная граница unsafe worktree cleanup

Core `89997df995df7c39b713e16aba216ecb19c8f497`, неизменённый production binary.
В каждый из двух итоговых passes входят три реальных root→child stdio сценария.
Это дополнение к известной проблеме unsafe cleanup, **не новый независимый P1**.

## Ручные Git index flags: tracked результат удаляется

В новом обычном child checkout синтетический workflow выполняет одно из:

```sh
git update-index --assume-unchanged base.py
# отдельный сценарий:
git update-index --skip-worktree base.py
```

Затем он переписывает tracked `base.py` новой реализацией и завершает task успешно.
В обоих сценариях:
- `git status --porcelain` пуст;
- `git status --porcelain --untracked-files=all` тоже пуст;
- `git ls-files -v` подтверждает соответственно `h base.py` либо `S base.py`;
- TaskTool возвращает `ok=true`, `status=completed`, `[worktree: no changes, removed]`;
- после task файл и checkout отсутствуют, managed branch удалена;
- новая реализация не была staged/committed и отсутствует в корневом HEAD.

Оба варианта дважды воспроизведены на свежих репозиториях. Git-only контроль
также подтвердил, что штатный `git worktree remove` сам по себе не защищает от
такой потери: он вернул 0 и удалил изменённый tracked файл.

### Узкая предпосылка

Flags выставлены **внутри child index явными командами fixture**.
Не утверждается, что они наследуются автоматически из обычного parent index,
что такие команды выдаёт штатная модель или что большинство пользователей
используют этот режим. Это реальный, но условный вариант выполнения Git
операций ребёнком. Никаких malicious tools или смены branch не требуется.

## Обычный sparse checkout: негативный контроль, не дефект

Parent до запуска Proteus настроен штатно:

```sh
git sparse-checkout init --cone
git sparse-checkout set included
```

Новый worktree наследует sparse layout: `service/base.py` отсутствует, initial
`git ls-files -v` содержит `S service/base.py`. Child создаёт этот путь и пишет
новое содержимое, **не выставляя flags вручную**. Следующая Git inspection
автоматически снимает skip-worktree с materialized файла:

```text
initial: S service/base.py
status:   M service/base.py
after:   H service/base.py
```

Оба реальных прогона сохранили checkout и файл, facade выдал task_id.
Поэтому находку нельзя пересказывать как «обычный sparse checkout удаляет
результаты». Проверенный стандартный sparse сценарий работает.

## Что это значит для исправления

Добавление `--untracked-files=all` закрывает ранее показанный
`status.showUntrackedFiles=no`, но **не является полным доказательством
отсутствия изменённых tracked files**. Git status и worktree remove одинаково
уважают вручную выставленные index flags.

Консервативный cleanup должен учитывать flags/реально материализованные
tracked paths либо удерживать checkout, когда их неизменность не доказана.
Не следует без запроса менять user index flags или автоматически коммитить
результат ради удаления. Этот опыт не закрывает отдельные lifetime/nested
ignored-store проблемы.

Доказательства: `pass*/index-assume-*`, `pass*/index-skip-*`,
`pass*/index-sparse-*`; `index-flags-git-only.json` — дополнительный низкоуровневый
контроль. Итоговые assertions включены в `verify.py`.
