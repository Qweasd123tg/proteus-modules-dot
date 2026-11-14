# Proteus Modules focused review

Date: 2026-11-12 UTC. Source revision: `3270dc0f894eaf4d0360306052b806099b8f5351`.
Contracts dependency: `b5fac84245b075896c24763b3aebac79b4375c2e`.
Review copy: `/workspace/scratch/3ba0fff8d310/audit-tools-modules`.
Only review tests were appended locally. No production code or remote changes.

## 1. Concurrent edit_file loses a successful edit (P2, reproduced)

Two independent tool invocations edit disjoint markers in the same 1 MiB UTF-8 file. Both return `ok=true`, but one change is lost. On the first attempted race, NEW_A was absent and NEW_B present. Atomic replacement protects against partial writes, not stale read/modify/write. The implementation reads the original file, prepares the replacement, then commits without preimage checking or a shared file lock.

The ordinary tool spec advertises `supports_parallel_tool_calls=false`, which fences one tool batch. This test directly exercises two module invocations, as could occur from separate sessions/agents or alongside an editor; it is not a full end-to-end multi-agent scheduling test. Root should not claim that one serial batch races.

Source: https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/file-tools/src/edit.rs#L130-L179

Suggested correction: serialize the complete read/match/write transaction for cooperating writers by canonical workspace/path across relevant workers, and detect changed preimages before publication. Revalidation alone is not an atomic compare-and-swap.

## 2. Large PTY input blocks cooperative cancellation (P2, reproduced)

Start `exec_command` with `tty=true`, command `stty raw -echo; printf READY; exec sleep 10`, yield 250 ms. Send 65,536 input bytes via `write_stdin`. Toggle the host cancellation flag after 200 ms. The invocation is still blocked 500 ms later. Even after independent session termination and `leader_exited=true`, the write stayed blocked for the additional one-second observation.

Reason: `PtyControl::write` calls blocking `write_all` and `flush`, while `write_stdin_impl` polls cancellation only before the write and in the later output wait. A child that does not drain its terminal input fills the kernel buffer. Later interactions are also serialized behind this call.

This is a real backend/tool-level test, not a GUI or process-host timeout test. A host may eventually kill the entire module; that does not make cooperative cancellation work. The isolated test process exits after measurement, removing its blocked writer thread; the child was independently terminated.

Sources:
- https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/shell-tool/src/unified_exec/process.rs#L120-L129
- https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/shell-tool/src/unified_exec.rs#L218-L247

Suggested correction: bounded, nonblocking writes with cancellation/deadline polling, and a limit or chunking contract for input. Do not hold the interaction hostage behind an uninterruptible write.

## 3. Valid UTF-8 stream is corrupted at polling boundary (P2, reproduced)

Command emits UTF-8 emoji bytes F0 9F, sleeps 0.8 s, then emits 98 80. First call yields after 250 ms, second polls to exit. Although the complete output is valid UTF-8 for one emoji, the outputs are U+FFFD and two U+FFFD characters; both report `truncated=false`, exit is successful. `wait_and_collect` takes all bytes, and `render_result` lossy-decodes each invocation independently, without retaining an incomplete scalar prefix for the next poll.

Source: https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/shell-tool/src/unified_exec/output.rs#L60-L93

Suggested correction: retain up to three incomplete trailing UTF-8 bytes between live polls; distinguish truly invalid data and final EOF from an incomplete scalar in a live stream. Raw capture is optional and does not repair the model-visible output.

## 4. read_many_files silently drops malformed UTF-8 suffix (P3, reproduced)

A six-byte file `b"valid\xc3"` returns `ok=true`, text `valid`, `original_bytes=6`, `returned_bytes=5`, and `truncated=false`. The helper meant to trim a budget-split scalar is also used when the entire file was read. Thus a genuinely incomplete final scalar is hidden instead of rejected or reported.

Source: https://github.com/Proteus-harness/Proteus-modules/blob/3270dc0f894eaf4d0360306052b806099b8f5351/tool/file-tools/src/read_many.rs#L250-L281

Suggested correction: use strict UTF-8 decoding when EOF is known and no budget truncation happened; trim partial scalar only at an intentional budget boundary and report truncation.

## Verification and reproduction

Official isolated Rust 1.95.0 toolchain. The unmodified baseline tests for file-tools, git-tools and policy-pack passed 46/46. Four added tests demonstrate the bugs, so their PASS means the defect was observed, not fixed. No full gate, live model, or GUI run was performed by this reviewer.

Commands after applying `repro-tests.patch` to the pinned source:

```
source /workspace/shared/proteus-toolchain/env.sh
cargo test --locked -p file-tools -p git-tools -p policy-pack --lib
cargo test --locked -p file-tools --lib review_ -- --nocapture
cargo test --locked -p shell-tool --lib review_large_pty_input_does_not_observe_cancellation -- --nocapture
cargo test --locked -p shell-tool --lib review_utf8_split_across_polls_is_corrupted -- --nocapture
```

Run the PTY reproducer as its own short-lived test executable, not alongside other work in one persistent process. Logs and the test-only patch are included in this directory.
