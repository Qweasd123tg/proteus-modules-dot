# Предложение: session-owned shutdown

**Design-only. Runtime не исправлен. Все 28 предложенных regression-сценариев не реализованы и не запускались.**

Цель: заменить разрозненные cleanup-заплатки единым владельцем live session, который закрывает admission, владеет peers/readers/monitors и подтверждает завершение эффектов перед удалением или заменой session.

- [Дизайн и source facts](DESIGN.md)
- [28 будущих regression contracts](TEST-CONTRACTS.md)
- [Результаты read-only review и открытые gates](REVIEW.md)
- [Статус проверки и SHA256 документов](VALIDATION.json)

База: Core `89997df995df7c39b713e16aba216ecb19c8f497` + delivery PR87 → PR88 → PR89; итоговый tree `00a3c04a70d7927d1688ea155142025f596a2874`.

Rust toolchain (`cargo`, `rustc`) и подготовленный Modules fixture были недоступны при подготовке. Rust build/test/fmt не выполнялись. Команды в TEST-CONTRACTS.md предназначены для будущей реализации, а не являются журналом проверки.

Ожидаемый выигрыш: единый lifecycle contract вместо отдельных cleanup-проверок, изоляция same-ID reopen и old-epoch handles, явная ошибка вместо ложного успешного shutdown. Выигрыш в LOC, производительности и количестве устранённых дефектов пока не измерен. Background routing, call-ID projection, worktree naming и остановка всех OS-внуков не входят в это предложение.

В пакет не включены исполняемые скрипты, raw WIP, runtime patch или логи. До реализации остаются обязательными design decisions: coherent service/facade binding, aggregate capacity owner, фактический I/O completion fence и host-wide admission.
