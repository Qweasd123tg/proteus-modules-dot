# Повторение без подключения модуля

**Официальный вариант.** Каталог word-count является отдельным Cargo workspace. Нужен Rust/Cargo 1.95.0, кэш Git-ревизии SDK из манифеста и зависимости из его Cargo.lock. Официальный [starter](https://github.com/Proteus-harness/Proteus-core/blob/c2cbadee518788f306ffb2b5271036b2658ea8cc/examples/modules/rust-tool/README.md#L13-L22) документирует сборку с Git-доступом. Наше дополнительное ограничение «строго оффлайн»:
```sh
cd word-count
cargo build --locked --offline --bin proteus-word-count-example
cargo test --locked --offline --lib -- --nocapture
```
На стенде первая команда с этим конкретным Git pin не прошла разрешение зависимостей. Вторую на этом pin не выдаём за проверенную.

**Отдельно проверенный оффлайн-вариант.** Для него необходим уже имеющийся неизменённый checkout [Core b2c285f](https://github.com/Proteus-harness/Proteus-core/tree/b2c285fcc317379ab47e484945afb7fc2b436331) и соответствующие crate-зависимости в локальном Cargo-кэше. Из корня этого комплекта:
```sh
python3 offline/prepare.py /path/to/existing/Proteus-core work-local
cd work-local
cargo build --locked --offline --bin proteus-word-count-example
cargo test --locked --offline --lib -- --nocapture
```
prepare.py создаёт только новый каталог, проверяет commit, меняет источник зависимости в копии Cargo.toml и кладёт проверенный альтернативный Cargo.lock. Rust-файлы в двух вариантах идентичны. Нарочно нет команд для запуска, подключения, установки или вызова worker. Имя бинарника — proteus-word-count-example, объявление экспорта — tool/example.word_count, задуманное имя инструмента — count_words. Последние два указаны в исходнике, не проверены через регистрацию.

**Что означает результат.** Выход ответа — текстовое десятичное число. Например, аргумент {"text":"two  words\nthree"} даёт output "3" и сохраняет id внутреннего тестового вызова. Здесь «слово» — непустая последовательность, отделённая Unicode-пробелом, а не лингвистическая токенизация: co-op и 東京 без пробела дают 1. В тесте отклоняются отсутствующий, лишний и не-строковый аргументы; это тест нашего слоя, не обещание сообщения об ошибке от SDK/хоста.
