Historical PR85 F4, not a current normal-provider incidence claim.

## F4. P3 / robustness: a wholly missing usage row is dropped instead of making totals unknown

Sources: [adapters.py 239–260](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/adapters.py#L239-L260).

Both Codex and Pi adapters filter out completed messages lacking a dict-valued usage block before `sum_usage`. `sum_usage` can consequently check only the surviving rows, unlike the Core measurement helper that counts expected requests.

Synthetic Pi fixture: two completed assistant replies, only one usage block (10 input + 100 cached, 5 output). Result: `model_requests=2`, `pipeline_ok=true`, and complete input 110 / output 5 rather than unknown. The analogous Codex two-turn fixture has the same totals issue. A missing field *within* an existing usage dict correctly becomes unknown; the existing regression tests cover that case but not an absent whole row.

Boundary: no evidence that the pinned Native Pi normally omits its required usage object. Treat this as malformed/incomplete artifact robustness, lower priority than F1–F3, not a demonstrated normal provider behavior.

Fix direction: retain an empty placeholder per expected completed reply/turn, make strict totals unknown if any contribution is absent, and separately expose observed sums/counts.
