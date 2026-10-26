# Статус проверки отдельной mixed-pin пары

2026-10-26: source composition; hosted lock-only resolution и независимый review
ещё ожидаются. **0 из 11 Core checks выполнены для Core1fc**. Локальный Cargo
не запускался. Cargo.lock пока является seed из PR10, не итоговым lockfile.

Старые результаты PR10 относятся только к Core3f. После lock/graph review
нужен отдельный exact-head runtime run и повтор CI draft PR. Все failed
receipts сохраняются; зелёный job без проверки содержимого artifact не считается
принятием. Scope и ограничения указаны в README.md.
