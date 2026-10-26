# Реальный research consumer: проверить строку источника, а не довериться пересказу

## Вопрос отчёта

В Round3 исследуется различие между raw observation и сообщением, подготовленным для LLM. Для конкретного утверждения reviewer хочет независимо проверить, что сохранённый source artifact действительно содержит выражение, объединяющее observation content и context extension. Это byte-level prerequisite для проверки вывода, **не автоматическая оценка истинности всего утверждения**.

Источник: [OpenHands ObservationEvent.to_llm_message, pinned lines66–72](https://github.com/OpenHands/software-agent-sdk/blob/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50/openhands-sdk/openhands/sdk/event/llm_convertible/observation.py#L66-L72).

Полный файл в уже полученном read-only snapshot:

- repository: `OpenHands/software-agent-sdk`;
- commit: `ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50`;
- path: `openhands-sdk/openhands/sdk/event/llm_convertible/observation.py`;
- Git blob: `139d90c5c5be4a18b458acb48158a215eed6fe88`;
- SHA256: `14eb6d888914a8d6a5ea205b7b4edd95b98c454d20d218256df3f0f26ac7e159`;
- length:7371bytes;
- exact fragment at half-open UTF8byte span[2514,2590),76bytes.

Local SHA256/size/Git-blob and fragment byte position were checked by read-only standard utilities. The matching pinned tree/connector/local blob chain is separately recorded in `source-manifest.json` and `hash-verification.txt`. The verification tool does not itself establish that retrieval chain.

## Operator setup

Оператор помещает разрешённый неизменённый artifact в `artifacts/openhands/observation.py` под выбранным invocation cwd и регистрирует source ID. Это подготовительный human/operator шаг, **не действие модели и не новая файловая возможность модуля**. Профиль должен уже разрешать выбранный `read_file` через обычные Core admission/policy rules.

```json
{"schema_version":1,"sources":[{"id":"openhands-observation-ce5716","path":"artifacts/openhands/observation.py"}]}
```

## Research request

```json
{
  "source_id": "openhands-observation-ce5716",
  "expected_sha256": "14eb6d888914a8d6a5ea205b7b4edd95b98c454d20d218256df3f0f26ac7e159",
  "claims": [{
    "claim_id": "llm-content-includes-extension",
    "start_byte": 2514,
    "end_byte": 2590,
    "quote": "content=list(self.observation.to_llm_content) + list(self.extended_content),"
  }]
}
```

Tool самостоятельно запрашивает configured path через host, проверяет full-read envelope и digest всего returned buffer, затем сравнивает эти76bytes. Успешный witness связывает source ID, configured/observed paths, config digest, content digest и текущие verifier/reader call IDs. Reviewer отдельно проверяет контекст функции и допустимость вывода. `origin_verified=false` и `semantic_entailment=not_evaluated` остаются обязательными даже для этого source-pinned сценария.

## Практическое обнаружение drift

- Иная версия source при старом expected hash: digest mismatch, никаких positive claims.
- Локальное newline conversion: digest mismatch, offsets не «исправляются» автоматически.
- Верный hash, неверная цитата или смещённый span: отказ, без fuzzy search.
- Reader/hook возвращает truncated/redacted/ranged content: отказ по envelope до сравнения hash.
- Содержимое источника после успешного read меняется: witness продолжает описывать только наблюдавшийся buffer; он не является persistent freshness lease.
- Успешная проверка этой строки не доказывает, что произвольный внешний browser/tool effect состоялся, и не даёт право записать память или пройти Hermes test gate.

**Runtime status:** request подготовлен и byte position сверена; module/actual-Core invocation для данного artifact **не выполнен**. Authored Rust fixtures модуля остаются независимыми от выполнения upstream-кода. Публикуется только маленький source fragment/request, не полный чужой checkout.
