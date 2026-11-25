# OpenCode workflow: defer the first copy of decoded history

The installed JSON bridge can read the decoded source history without copying its outer array. The workflow takes a private copy only just before its first append, if it has not already adopted a separately decoded replacement. Direct callers retain the original eager copy. On an unchanged successful history this delays a copy; on pre-append failure or a verified replacement it can avoid that copy entirely.

Local tests exercised the exact OpenCode workflow and installed worker with inert upstream dependencies. Twenty paired workflow cases matched, along with three byte-for-byte local JSON broker scenarios (ordinary success, verified replacement, and early failure). A held prepare for 8,192 ordinary messages showed that the old outer copy was not present in the candidate. Under replacement or early failure it was never needed.

No full Core, real provider, tool execution, application timing or RAM was measured. Apply source.patch to the live two-file base from the receipt. If the exact cumulative runner already includes #739, #747 and #751, use the alternative from receipt.json instead, not both:

```sh
python3 -c 'import json,sys; sys.stdout.write(json.load(open("receipt.json"))["alternate_scoped_patch"])' > scoped.patch
```
