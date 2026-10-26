# Evidence-spans validation

Source-reviewed CI candidate; exact-head Rust runtime validation is pending at initial publication. No local compile/test pass is claimed.

From the repository root, official Rust 1.95.0 and Python 3.11+ (the workflow also records source/toolchain provenance):

```sh
set -euo pipefail
mkdir -p validation
python3 -B -I examples/evidence-spans/ci/verify_artifacts.py --initialize-leaf validation/evidence-spans
python3 -B -I examples/evidence-spans/ci/test_controls.py 2>&1 | tee validation/evidence-spans/validator-controls.log
CARGO_TARGET_DIR="$PWD/target" bash examples/evidence-spans/ci/run.sh
```

The gate requires exactly 39 named Rust tests: 32 policy, 5 pure reader-helper, 2 own-executable SDK wire. Zero failed, ignored, measured or filtered tests. Format, positive/negative example outputs including the exact non-authenticity disclaimer, exact typed receipt fields, config/profile equality, source digest and both quote spans are independently checked. The 23 Python controls use invented logs/results and are reported separately with exact name and summary checks; they are not Rust/actual-Core evidence. The evidence leaf must be newly created atomically; existing evidence is not reused or deleted. Upload and inventory require successful input recording, so a stale-leaf rejection cannot publish old evidence.

The dedicated workflow records every source/lock/fixture/CI input SHA256 before execution, checks it again afterwards and uploads only validation/evidence-spans, with a per-file byte/SHA256 manifest. Inspect both exact-head job status and downloaded artifact, not just a green badge. Inherited validation outputs from other examples are not this increment's evidence.

Limits: synthetic host/read callbacks; no actual Core registry/policy/approval assembly, real read_file deployment, upstream suites, provider calls, browser actions, crash/fault-injection test, origin authentication or semantic proof. A successful demonstration process can contain a negative ToolResult: the gate checks the exact negative diagnostic and absence of positive evidence.

PUBLICATION.json maps the source-reviewed snapshot to public paths and records doc-only adaptations. No broad Core changes or automatic memory mutations are part of this module.
