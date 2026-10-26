#!/usr/bin/env bash
# Only this authored overlay and the unchanged, separately pinned package gate.
set -euo pipefail
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --no-self-update
python3 -B -I "${PROTEUS_ENVELOPE_PACKAGE:?absolute overlay directory}/test_envelope.py"
bash ci/run.sh
