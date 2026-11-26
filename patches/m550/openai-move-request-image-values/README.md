# Move image values into the OpenAI request

Avoid cloning a local image data URL into its JSON block, then copying the
block again when it starts a new message. Preserve field ordering, grouping,
attachment errors, and phase metadata behavior.

Apply on exact Modules stock `345585a91d9f7bac7cef971db68e41569f97a672`.
Before applying, verify `git hash-object model/model-pack/src/adapters/openai/request.rs` equals
`0aba7e994e9ec98497ef85c52dbe76b40ebba0ad`. The exact preimage already includes #694.
Do not apply after #832, #835, or both: a combined variant is not provided.
Apply and reverse checked on the exact stock tree.

Two optimized unmasked model-pack libraries built. 12
focused native tests passed in both arms. The identical-byte 256 KiB PNG
image-first case went from 3 to 1 allocation requests at least one
URL long; text-only was unchanged. Same-message image after text removes
one such request; two images starting a message remove three. This is
scoped allocation traffic, not elapsed time or whole-app memory.
