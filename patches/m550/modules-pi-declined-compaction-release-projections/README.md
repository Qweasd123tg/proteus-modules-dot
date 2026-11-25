# Pi: stop retaining projected rows when compaction is declined

The Pi pre-sampling hook normally projects an entire history before checking whether it needs compaction, even when the workflow already supplies a token estimate. On the installed JSON-line worker path, when a typed estimate and unmodified pre-sampling output qualify, use Pi's pinned decision predicate first. If the predicate declines compaction, still convert every row, with the same chronological tool-name map and validation, but do not collect the results. The original messages remain available; this change removes only the temporary projected vector from that branch.

Positive compaction still receives its converted rows. Missing or unsupported hints and direct JS entry points retain the original route. This does not change the worker protocol, model selection, approvals, signal handling, or hook responses. Tests use exact project sources and the pinned predicate with inert SDK/service components; they do not measure production memory or speed.

Apply `source.patch` to the pinned Modules owner preimages, or extract the exact alternative below if #740 and the #756 scoped variant after #740 are already applied. The two variants are the same logical patch; never apply both. To compose the three changes use that chronological order; raw #756 is not intended to apply after this new owner patch.

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
