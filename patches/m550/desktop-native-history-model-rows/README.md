# Native-history benchmark: separate displayed and model history lengths

An optional benchmark setting asks the pinned seeder to keep only a specified number of rows in active model history while retaining the full displayed transcript. The existing Core verifier checks both, and the Desktop runner reports the distinction. Omission keeps the historical seeder and verifier behavior.

Pass `--messages 50000 --model-history-rows 100` with the normal runner arguments for a distinct compacted-journal scenario. It is not a same-input A/B of the 32 MiB storage projection cap: the compacted fixture has a different journal shape.

Local verification ran the exact Desktop runner and the pinned Core Python verifier, using an inert stand-in seeder and mocked application stages. All 18 controls passed: omission preserved the old command and report, specified model counts were checked independently from displayed rows, and invalid requests or incorrectly seeded tails failed before the application stage. Owner and cumulative runner unit tests passed in all four arms.

No native seeder or application was launched. This enables a future measurement; it does not provide startup, memory, or projection-route measurements.

Apply `source.patch` to the live runner base recorded in the receipt. If #748 and #750 are already applied, use the alternate patch in `receipt.json` instead (not both):

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > after-748-750.patch
```
