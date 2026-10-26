# Статус проверки отдельной mixed-pin пары

2026-10-26: hosted lock-only CI [40300268434](https://github.com/Qweasd123tg/proteus-modules-dot/actions/runs/40300268434)
на `f0260bc8a84c4e77e8494475a659c50e0c3c0724` прошёл: resolution,
locked fetch и полные offline metadata двух графов; 7 стадий exit0.
Новый lock меняет только пять Proteus Git source identities3f→1fc.
Registry versions/checksums/dependency edges не менялись; portable graph/lock
сохраняет SDK3f. Подробные identities — `LOCK-DELTA.json`.

**0 из 11 Core checks выполнены для Core1fc на момент composition**.
Новый runtime workflow публикуется только после независимого graph/source review;
его exact-head результаты и повтор draft PR должны быть проверены отдельно.
Локальный Cargo не запускался. Старые результаты PR10 относятся только к Core3f.

Все failed receipts сохраняются. Зелёный job без проверки artifact не является
принятием. Scope и ограничения указаны в README.md. Это не universal current-Core
compatibility и не проверка full agent turn.
