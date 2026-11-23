# Paired R24 cold-checkpoint diagnostic

A real patched R24 child, fresh external stock JSONL worker and local model-free fixture over stdio. All turns, mutations and checkpoint proofs are emitted by the running product. No external model or repository/network access is needed. Seeding inserts synthetic assistant messages in batches ≤350 for the widths below. A last turn does a genuine changed compaction, preserving only the final input and one reply in active history. This does **not** clear the display archive. Each fixture uses one seed workspace, session and checkpoint; measured cold attachments do not send a model turn.

## Run

Python 3.11+ on Linux. Get the R24 patched CLI supporting `--parkable-child` and `--resume-child-checkpoint`, compatible stock JSONL and reference modules, and the matching core examples/modules directory containing `component_runtime.py`. Export their absolute paths:

```sh
export PROTEUS_PEER_CLI=/path/to/patched/proteus
export PROTEUS_TEST_SESSION_STORAGE_MODULE=/path/to/stock-jsonl-worker
export PROTEUS_TEST_REFERENCE_MODULE=/path/to/proteus-reference-module
export PROTEUS_EXAMPLE_MODULES=/path/to/R24/core/examples/modules
python3 -B probe.py --shape both --rows 1050 --width 175 --reps 3 --output paired.jsonl
python3 -B probe.py --shape confirmation --rows 5000 --width 175 --reps 3 --output confirmation.jsonl
python3 -B summarize.py paired.jsonl confirmation.jsonl
```

Run in this directory; an output file must be new. Real run manifests include binary hashes. Only Python fixture code is written alongside the probe; the SDK and executables are external dependencies. All session/fixture data lives in a new temporary private tree, removed on normal exit. Raw stdout frames and synthetic row contents are not emitted into result files.

## Arm integrity and boundaries

- A non-measured cold launch with the disposable display head withheld naturally builds the view. Verify the saved outer and inner source revisions agree with the parked proof; save the original head.
- Alternate pairs (present/missing, missing/present, present/missing). For each arm, create a *new* child process at the **same existing canonical path**. Manually change only the opaque display-head file; preserve other cache pages, catalog and journal. Present restores the original head bytes if needed; missing withholds the head. The stock worker can maintain its ordinary derived cache state. Check journal SHA-256, inode, device, byte size, mtime and ctime before and after every timed arm. Check the exact returned checkpoint and distinct physical root IDs.
- Clock starts before launching the peer. Immediately send a uniquely identified 80-byte JSONL checkpoint request. Timestamp each complete newline-terminated stdout frame in a draining Python reader before parsing **that** frame. Times include process start, OS scheduling, child→Python pipe I/O, and, where applicable, draining/parsing earlier frames. They are not nonoverlapping in-process profile spans. No retries. Report bytes including newline; cumulative bytes are child→reader traffic only (not worker RPCs).
- This measures a fresh process under uncontrolled (likely warm) OS page cache. Explicit journal digest checks read the small synthetic journal. Measurements are not disk-cold benchmarks. Report ranges and paired sample counts; medians of phases need not add up. No valid inference here about a native parent's admission latency, first Send/recall, production workloads, RSS, traffic between child and storage, or the exact functions responsible for extra time.
- `paired-1.jsonl` is the stable-inode short/moderate run; `confirmation-1.jsonl` is its larger independent fixture. The earlier `short-1.jsonl` used a different session-copy setup and `moderate-1.jsonl` stopped during fixture validation; **neither** contributes to the table.
