#!/usr/bin/env bash
# From the pinned core checkout after applying the R24 candidate patch.
set -euo pipefail
: "${PROTEUS_TEST_REFERENCE_MODULE:?path to the already-built reference test component}"
: "${PROTEUS_TEST_SESSION_STORAGE_MODULE:?path to the stock JSONL worker}"
# The process_agent_pool target uses Cargo's built proteus binary unless an
# explicit override is present. Never run this gate against a stale override.
unset PROTEUS_TEST_BINARY
export PYTHONDONTWRITEBYTECODE=1
python3 scripts/test.py -p proteus-core --test process_agent_pool --test process_agent_control -- --nocapture --test-threads=2
