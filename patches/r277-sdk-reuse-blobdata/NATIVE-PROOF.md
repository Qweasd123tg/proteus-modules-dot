# Native replay

These probes exercise the locked `proteus-session-storage-module` executable. Run them against four separately built and frozen uninstrumented release workers (stock and candidate, default `serde_json` features and `preserve_order`); then run the optional test-only meter on the separately rebuilt default-mode arms. It should be impossible to pass candidate-vs-stock replay by passing the same frozen executable twice.

```sh
python3 -B native_protocol.py --stock /path/to/stock --candidate /path/to/candidate \
  --features default --large --work /fresh/path
python3 -B native_protocol.py --stock /path/to/stock-preserve --candidate /path/to/candidate-preserve \
  --features preserve_order --large --work /fresh/path
```

The stock worker creates, materializes and closes the JSONL or SQLite session, including real PutBlob, metadata, and cache operations. Each arm reads the same files and locator with the same wire IDs. The cap-only files are filled directly so an oversized input frame can't substitute for measuring output. The two arms compare original stdout bytes including LF, not a normalized reserialization. Each successful blob read validates payload length, Python Base64/SHA-256 and persisted bytes. The large fixture includes a valid PNG at the normal 5 MiB image cap, another real object at the 64 MiB raw storage cap, precise default 8 MiB and explicit launch cap checks (including LF), and an oversized output that must end the worker after writing no result bytes. Both methods, base64 padding variants, errors and unrelated metadata/cache requests are covered. The HTTP /image route is source-verified, not exercised by this worker replay.

```sh
# WORK is the completed replay_worker.py work directory.
WORK=/path/to/worker-replay
METER=/fresh/meter-work
TOOLS=/path/to/rust/bin
mkdir -p "$METER"/{native,cargo-home,target,tmp}
cp -a "$WORK/native/stock" "$WORK/native/candidate" "$METER/native/"
ln -s "$WORK/vendor" "$METER/vendor"
python3 -B instrument_native.py "$METER/native/stock" "$METER/native/candidate"
python3 -B - "$METER" "$TOOLS" <<'PYTHON'
from pathlib import Path
import shutil
import sys
from replay_worker import BIN, pick
from worker_inputs import cargo, need
work, tools = map(lambda p: Path(p).resolve(), sys.argv[1:])
for arm in ("stock", "candidate"):
    cargo(work, tools, arm, "clean", "--release", "-p", BIN, "-p", "proteus-module-sdk")
    raw = cargo(work, tools, arm, "build", "--release", "-p", BIN, "--bin", BIN,
                "--message-format=json", capture=True)
    sdk, binary, serde = (pick(raw, name) for name in ("proteus_module_sdk", BIN, "serde_json"))
    need(not sdk["fresh"] and not binary["fresh"], "fresh instrumented executable and SDK")
    need("preserve_order" not in serde["features"], "default-mode meter")
    need(Path(binary["manifest_path"]) == work/"native"/arm/"components/session-storage-module/Cargo.toml",
         "instrumentation must run the native worker")
    shutil.copy2(binary["executable"], work/f"{arm}-meter")
PYTHON
python3 -B native_meter_replay.py --stock "$METER/stock-meter" --candidate "$METER/candidate-meter" \
  --work /fresh/meter-fixture
```

The meter counts Rust allocations and reallocations of at least 64 KiB originating on an invocation's SDK thread after request validation. It records pre-conversion backend peak, then resets counters while retaining live balances. Generation IDs distinguish a cloned string allocation from the original even if pointer addresses could later recur. Logical request peak is the max of both phases; it is not process RSS, allocator overhead, Linux page cache or host decoding. One- and four-response controls leave stdout unread until Linux reports a worker blocked in pipe write and the other invocations behind the writer lock. The probe verifies equal live payload bytes awaiting output, returned generation through write/flush, and zero residual tracked bytes after drop. The meter is test-only and excluded from source.patch. It needs a Linux procfs that exposes own-child wait channels.
