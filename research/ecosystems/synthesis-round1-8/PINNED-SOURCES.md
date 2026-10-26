# Закреплённые источники synthesis

Таблица сохраняет отдельные pins, включая навигационный README и исторический архив. Это не13независимых систем и не количество новых находок. Механизмы основаны на selected read coverage исходных отчётов; ни один upstream runtime не исполнялся.

| Round | Репозиторий | Pin | Ограничение |
|---|---|---|---|
| 1 | `browser-use/browser-use` | [3df5806a0d097a1546d92c49bcf1b28c9972c3bd](https://github.com/browser-use/browser-use/commit/3df5806a0d097a1546d92c49bcf1b28c9972c3bd) | Selected pinned source consumers; no upstream execution |
| 1 | `google/adk-python` | [bf6739723c1b8b03bff8bb1e6ffada4d88098fcf](https://github.com/google/adk-python/commit/bf6739723c1b8b03bff8bb1e6ffada4d88098fcf) | Selected pinned source consumers; no upstream execution |
| 2 | `letta-ai/letta-code` | [1fb6ea4d30942ef9220b096ba7f4185f18184fc1](https://github.com/letta-ai/letta-code/commit/1fb6ea4d30942ef9220b096ba7f4185f18184fc1) | Active code source at observed research date; not V1 API |
| 2 | `letta-ai/letta` | [56ba9c25552605eec89de8ed3dc6394b625c1993](https://github.com/letta-ai/letta/commit/56ba9c25552605eec89de8ed3dc6394b625c1993) | Historical retired V1 archive, not active Letta Code |
| 2 | `strands-agents/harness-sdk` | [10b9393ef705ccf4b56e5fe0d81e0712c0d97efe](https://github.com/strands-agents/harness-sdk/commit/10b9393ef705ccf4b56e5fe0d81e0712c0d97efe) | Selected pinned source consumers; no upstream execution |
| 2 | `letta-ai/letta` | [8816d3a8516893bfdc0fa14bfb1235226012e295](https://github.com/letta-ai/letta/commit/8816d3a8516893bfdc0fa14bfb1235226012e295) | Navigation README only: retirement/routing |
| 3 | `OpenHands/software-agent-sdk` | [ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50](https://github.com/OpenHands/software-agent-sdk/commit/ce5716a3c0a955a85bb0cc4dcfaa94d5fefcda50) | Selected pinned source consumers; no upstream execution |
| 4 | `pydantic/pydantic-ai` | [715651ef7fd3994395e85070ba3d6096c5b211c9](https://github.com/pydantic/pydantic-ai/commit/715651ef7fd3994395e85070ba3d6096c5b211c9) | Selected pinned source consumers; no upstream execution |
| 5 | `langchain-ai/deepagents` | [f26eb54c9b9f66d2ea7edbb9748413d58744534d](https://github.com/langchain-ai/deepagents/commit/f26eb54c9b9f66d2ea7edbb9748413d58744534d) | Independent pin; no installed pair with selected LangChain proved |
| 5 | `langchain-ai/langchain` | [d57f1ea32caa10005e816589c9a12c48f4889815](https://github.com/langchain-ai/langchain/commit/d57f1ea32caa10005e816589c9a12c48f4889815) | Independent pin; no dependency lock/runtime pair claim |
| 6 | `mastra-ai/mastra` | [7aa49a5c5f5af219693479386f971d2c8dc8f123](https://github.com/mastra-ai/mastra/commit/7aa49a5c5f5af219693479386f971d2c8dc8f123) | Selected pinned source consumers; no upstream execution |
| 7 | `agentscope-ai/agentscope` | [bdad647d2fee7d66597681ecd89e086b7800dd2a](https://github.com/agentscope-ai/agentscope/commit/bdad647d2fee7d66597681ecd89e086b7800dd2a) | Selected pinned source consumers; no upstream execution |
| 8 | `livekit/agents` | [4c24224f0ef4f511fa3395dcd87b294a87ae241e](https://github.com/livekit/agents/commit/4c24224f0ef4f511fa3395dcd87b294a87ae241e) | Selected pinned source consumers; no upstream execution |

Core comparison: current source `1fc3ef223d10322815dd9290a50d045bc95402bb`, published SDK/Core `3f36a003b4f3fde2242fc80f7aedac00dd127d1d`. Ранние раунды использовали3f; поздние явно сравнивали выбранные объекты с1fc. Modules current source `7fceaebc3bed8add9b0e3091110f59deca86ba46`, legacy `04114bbe85f179895e2b8553b6169a284caaeae3`. Совпадение выбранных bytes не означает равенства полных деревьев или runtime совместимости.

Exact report/ledger/coverage/source-manifest SHA-256: [INPUTS.json](INPUTS.json). Обязательные уточнения Round6 также hash-bound отдельно; они не изменяют исходный report. Source-only prototypes и executed example receipts находятся в [STATUS.md](STATUS.md), не выводятся из этой таблицы.
