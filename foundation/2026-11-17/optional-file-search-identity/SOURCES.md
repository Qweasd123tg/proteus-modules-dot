# Source identities and consumer coverage

Все refs повторно проверены перед подготовкой публикации 2026-11-17:

| Источник | Ref |
|---|---|
| Core main | `cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d` |
| Modules main | `b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7` |
| Фактический Modules/Core dependency | `185225a7103088c444788374ca425d230060f55a` |
| Delivery base перед пакетом | `5a2e7987ad1bc2887cb05d5aa0af1fd968471e2e` |
| Desktop main, source-only consumer review | `79499f2d639a3185384bed75f29b6919b811fe7c` |
| Extensions main, source-only consumer review | `ae6479c5accc404d5a635fdeff1397a8b3016416` |
| OpenAI Node SDK | `4517ca801b79a93ccc17826b0b63ba2313355307` |

- [Official SDK Result schema](https://github.com/openai/openai-node/blob/4517ca801b79a93ccc17826b0b63ba2313355307/src/resources/responses/responses.ts#L3640): `file_id?: string`; Git blob `7b923820b319f45a3b645a657ddb38c5eb3abe48`. Это omission, не разрешение provider null.
- [Core hosted-tool DTO](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-contracts/src/domain/hosted_tool.rs): обязательный String в preimage; blob `23694a6a1f79420beeef2dbe042a9c8413ce6886`.
- [Modules item parser](https://github.com/Proteus-harness/Proteus-modules/blob/b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7/model/model-pack/src/adapters/openai/response/item.rs): required_string preimage; SHA-256 `82e84ac2239b2adbd1b9ac667db07b9629cd193fea25c1c4e34cad88b71a804a`.
- [Modules request mapping](https://github.com/Proteus-harness/Proteus-modules/blob/b7e3ca3c23b9440c8c1a9e1d15386d02ef8586c7/model/model-pack/src/adapters/openai/request.rs): `include_results` запрашивает provider results; HostedToolActivity не превращается в новый input-side tool invocation.
- [Core transcript projection](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/crates/proteus-core/src/app_server/transcript.rs): result count и activity JSON, без direct file-ID access.
- [Core alpha compatibility policy](https://github.com/Proteus-harness/Proteus-core/blob/cdf4aa5c1286f4d4dac31e7b7e52fccf3d1a3f4d/AGENTS.md): coordinated producer/consumer changes, без migration shims и второго формата.

Core/Modules direct-symbol search нашёл DTO, один Core constructor fixture, Modules parser и один pattern assertion. Все эти tracked uses включены в paired proposal. Generic serde consumers не объявляются квалифицированными этим поиском.

Reviewer source-only проверил Desktop transcript/tool-display пути (AppTranscriptTool/Value) и Extensions conversation view (envelope + raw JSON). Прямых FileSearchResult/file_id usages поиск там не обнаружил; это не доказательство полного consumer closure. Desktop всё ещё компилирует старый Core pin, поэтому coordinated rebuild и affected client gates обязательны.

До исследования прочитаны integration plan и HOLD registry. Это не повтор #165 terminal-reader/metadata transport cuts и не открытие typed-memory, priority, image relocation, deadline, process или security scopes. Upstream не менялся.
