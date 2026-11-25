# Core benchmark summary: retain only the fields used for idle statistics

After each full sample is parsed and evaluated by the existing interval policy, keep just the scalar fields needed to compute the report. The parser, interval eligibility, admissibility, error ordering, and final medians and peaks stay unchanged. Per-process details are not needed by this report's accumulator.

Thirteen local fixtures ran through each of four exact CLI arms. The reports and diagnostics matched. In a normal-size synthetic 48-sample interval with 25 process rows per sample, the accumulator retained 1,200 nested process rows before and none after; interval coverage stayed 47/48. The reader still reads and parses the same log, and these counts cover the accumulation list, not total process memory.

Apply source.patch to the current pinned file, or use the exact alternate included in receipt.json if #771 is already applied (not both):

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
