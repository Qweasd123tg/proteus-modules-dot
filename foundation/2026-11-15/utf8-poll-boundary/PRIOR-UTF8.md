# Known initial-modules finding (historical evidence, not rerun)

## 3. Valid UTF-8 stream is corrupted at polling boundary (P2, reproduced)

Command emits UTF-8 emoji bytes F0 9F, sleeps 0.8 s, then emits 98 80. First call yields after 250 ms, second polls to exit. Although the complete output is valid UTF-8 for one emoji, the outputs are U+FFFD and two U+FFFD characters; both report `truncated=false`, exit is successful. `wait_and_collect` takes all bytes, and `render_result` lossy-decodes each invocation independently, without retaining an incomplete scalar prefix for the next poll.

Source: https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/shell-tool/src/unified_exec/output.rs#L60-L93

Suggested correction: retain up to three incomplete trailing UTF-8 bytes between live polls; distinguish truly invalid data and final EOF from an incomplete scalar in a live stream. Raw capture is optional and does not repair the model-visible output.

