# Read-only check of the screenshot's Pi / Proteus Pi comparison

Source snapshot: Core `89997df995df7c39b713e16aba216ecb19c8f497`. No published file changed.

## Exact matching source

[2026-11-12-deepseek-clean.md](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/results/2026-11-12-deepseek-clean.md#L7-L23)
and its [JSON](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/results/2026-11-12-deepseek-clean.json).

| Quantity | Pi | Proteus Pi |
|---|---:|---:|
| seconds | 1558.5870583840049 | 1268.9937475269987 |
| minutes, exact arithmetic | 25.976450973066747 | 21.149895792116645 |
| minutes rounded to 1 decimal | 26.0 | 21.1 |
| input tokens | 936935 | 932601 |
| output tokens | 77784 | 64715 |
| full PASS | 9/9 | 9/9 |

All 45 selected rows match the existing short/long source reports in PASS, tokens, prompt hash and repo hash. Durations match at the millisecond precision preserved by the earlier short source. All five summary rows exactly reproduce sums from `selected_rows`. The long source's SHA256 matches the clean report's declared input digest.

## What “public 8/9” can mean

The matching source does NOT say 8/9 PASS: it says all five arms passed 9/9. The corpus composition does support **eight adapted public upstream tasks and one locally composed integration task**:

- Four Aider polyglot exercises: forth, poker, dominoes, variable-length-quantity.
- Four Terminal-Bench tasks: cancel-async-tasks, log-summary-date-ranges, db-wal-recovery, write-compressor.
- One composed multi-turn go-review, based on public sgf-parsing and go-counting, with a new integration requirement and private grader additions.

[corpus.py](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/corpus.py#L16-L19),
[long_go.py](https://github.com/Proteus-harness/Proteus-core/blob/89997df995df7c39b713e16aba216ecb19c8f497/examples/performance/coding-harness/long_go.py#L17-L51).

This is an inference about the supplied description “public 8/9”; the screenshot itself was not attached to this worker's task.

## Do the newly identified accounting defects invalidate this exact comparison?

**No demonstrated invalidation.** The four reproduced defects are real code paths, but the following source-specific evidence prevents treating them as proof that these particular numbers are wrong:

1. The timeout used in the partial-usage reproduction (`journal-segments` / Pi) is explicitly excluded from the clean table. Every selected Pi and Proteus Pi row has stored full PASS.
2. All three selected long Pi cases have recorded returncode 0, timed_out=false, failure_count=0 and usage_complete=true. Their Proteus Pi peers have no model failures: compressor has one tool failure, go-review has two tool failures, WAL has none. Tool failures are not the recovered-model-error asymmetry.
3. The final stop reason and per-reply native usage coverage are not retained by the published aggregates. Therefore the length-stop and absent-usage-row defects cannot be positively excluded using only these aggregate files, but neither is there evidence they occurred.
4. None of the identified token-accounting defects directly changes the recorded wall duration or the sum arithmetic. A misclassification could change cohort selection; no such actual selection error was established in these stored rows.

Raw target/result.json, stdout.jsonl and native/canonical journals were not present in `/workspace`; only their paths and aggregated extracts are versioned. The environment inventory exposed no connected user computer with the original runs. Full independent event-level regrading would require those raw artifacts.

## What the time difference actually measures

| Task | Pi seconds | Proteus Pi seconds |
|---|---:|---:|
| cancel-async-tasks | 319.564 | 191.599 |
| db-wal-recovery | 48.536 | 53.145 |
| dominoes | 60.749 | 314.635 |
| forth | 125.686 | 61.627 |
| go-review | 201.865 | 256.561 |
| log-summary-date-ranges | 59.371 | 51.896 |
| poker | 54.698 | 54.993 |
| variable-length-quantity | 39.808 | 35.889 |
| write-compressor | 648.310 | 248.648 |

The total difference is 289.593 seconds (18.5805%). Compressor alone contributes 399.662 seconds. On the other eight tasks combined, Proteus Pi takes 110.069 seconds longer (+12.0918%). Proteus Pi is faster on five of nine individual tasks; its median task duration is slightly higher (61.627 vs 60.749 seconds).

This does not invalidate the reported sum; it limits a general claim that the harness is intrinsically 18.6% faster. The published report already notes parallel runs/provider load, fixed historical runtime versions, and the common filtered subset. There is no causal repeated benchmark isolating a runtime-speed effect in these nine single first attempts.
