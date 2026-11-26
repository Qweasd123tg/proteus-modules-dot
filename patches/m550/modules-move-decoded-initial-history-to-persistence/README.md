# Modules: move the decoded initial history into the persistent view

After the workflow validates the admitted user message, it moves the decoded history into the persistent view instead of cloning it. The model still receives a separate copy, so prompt-only changes cannot alter persistence. TaskReceived, normal and continuation anchor checks, and checkpoint output stay the same. No JSON pass changes.

On exact standalone Modules sources, 116 stock and 117 candidate library tests passed. The focused cases covered unchanged rejection, ownership transfer and append-only checkpoint output. Separately, the actual Coding Workflow worker passed 12 detached invocations with the locked v3/v22 SDK, comparing #810+#812 with and without this patch. This verifies typed outcomes and callback order on the synthetic fixture, not the current Core application, durable writes, or runtime cost. No speed or RAM measurement was made.

Apply `source.patch` to the exact preimages in `receipt.json`. No alternate. #698 and #703 are already in the owner. #810 and #812 are optional.
