# Независимая read-only проверка

Проверено против Core tree `00a3c04a70d7927d1688ea155142025f596a2874`. Reviewer не менял файлы и не запускал код/tests.

В первом проходе выявлены и исправлены четыре неточности:

1. Producer quiescence отделена от доставки уже queued transport events и производной HTTP activity.
2. Для полного HTTP aggregate shutdown добавлены host-wide admission fence и гонка new/resume/remember_server.
3. Удаление global MAX_SESSIONS признано изменением aggregate capacity, а не сохранением прежних лимитов.
4. Reader stop/join выполняется независимо от kill/wait ошибок; ошибки агрегируются без short-circuit cleanup.

Также уточнена provenance: подтверждено совпадение tree, не исходной commit metadata.

Повторный review: все замечания учтены, новых блокеров для **design artifact** не обнаружено. Это не доказательство работающего shutdown и не одобрение несуществующего runtime patch.

Нерешённые implementation gates: согласованное service/facade binding, владелец aggregate capacity, фактический I/O completion fence, HTTP-wide admission и исполняемые regression checks. Все 28 сценариев в TEST-CONTRACTS.md пока предложены, не реализованы и не запущены.
