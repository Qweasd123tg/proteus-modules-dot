# Join instruction text with one sorting buffer

Keep one reference list and retain the original stable descending priority
sort. No trim is applied to retained instruction text: trim only decides
whether a block is empty. Reserve the final byte length and join the original
texts with the same two-line separator. No provider or wire shape changes.

Apply on Modules `345585a91d9f7bac7cef971db68e41569f97a672`. Historical #694 is already present;
there is no alternate required.

Both optimized unmasked libraries built from the exact current model-pack
scope. 11 focused native tests passed before and after,
including the OpenAI and Anthropic request renderers. A synthetic 128-block
prefix (109 retained) rendered exactly the same bytes, with 8 → 2
allocation/reallocation requests and 8215 → 4183 aggregate bytes
requested. Empty and all-blank controls were unchanged. No full-app
memory, latency, or provider traffic measured.
