# Core history-scale: hash auxiliary seeds without copying the history prefix

The explicit `--seed-model-requests` verifier used to make a shallow list copy of the whole canonical history prefix before each hash. A decoded list now supplies the same prefix as an iterator. The final payload row is still excluded from the history hash and validated separately. Attribution, exchange-count checks, message encoding and digest checks are unchanged. Non-list inputs still use the original slicing path.

The evidence is from the actual Python fixture verifier, not from a native Proteus run. In a fixture with three 4,096-row model histories, the digest still saw every history row in order, with no second list of 4,096 references per request. Journal parsing, the decoded list and message hashing remain.

Apply `source.patch` to the pinned file, or choose the exact alternate in `receipt.json` if #767 is already applied. Do not apply both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
