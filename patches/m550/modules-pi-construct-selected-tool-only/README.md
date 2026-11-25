# Pi: construct only the selected tool definition on invoke

A single invocation used to construct four Pi definitions and discard the three it did not use. On the pinned Pi SDK, use the existing single-definition factory after selecting from exactly the same four names, in the same order. The wider SDK factory is not used to admit additional names. The tool list still uses its original full factory.

The selected constructor, working directory, default options, argument parsing and preparation, signal, execution, and error/result handling stay unchanged. The inert paired invocations verify four-to-one definition construction while the selected execution remains one. This is not a measurement of application CPU or memory, and no real tool executed in the tests.

Use `source.patch` on the pinned Modules owner preimage. If #737 is already present on the exact supported basis, use the embedded alternate from `receipt.json` instead. Use one, not both. Any separately applied worker change is outside this patch.

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
