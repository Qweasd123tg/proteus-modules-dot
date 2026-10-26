# Авторский offline model/policy fixture

Только тестовая реализация model/v12 `smoke.strict_scripted` и policy/v2
`smoke.strict_policy`, SDK/Core3f. Не production policy и не live model.
Сценарий выводится из canonical history: точный write_file, затем verification,
затем кандидат final без собственного утверждения об успешной проверке.
Write требует Ask; вложенный reader можно отдельно запретить при сохранённой
видимости. Fixture не обращается к сети/файлам/shell и не подтверждает approval.

16 авторских Rust-тестов пока не исполнены для этого публичного пакета.
Их CI gate и фактические семь turns плюс direct denial описаны в
[`../strict-host/README.md`](../strict-host/README.md). Lock и Rust-исходники
сохранены без изменений; проверка с настоящим Core — отдельный обязательный слой.
