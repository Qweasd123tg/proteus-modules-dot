#!/usr/bin/env bash
# Proposed overlay only; original module and original semantic gates unchanged.
set -euo pipefail
rustup toolchain install 1.95.0 --profile minimal --component rustfmt --no-self-update
python3 -B -I ci/resource-envelope-v1/test_envelope.py
workspace=examples/evidence-spans
artifacts=validation/evidence-spans
mkdir -p validation
python3 -B -I "$workspace/ci/verify_artifacts.py" --initialize-leaf "$artifacts"
git rev-parse HEAD > "$artifacts/checkout-commit.txt"
find "$workspace" .github/workflows/check-evidence-spans.yml ci/resource-envelope-v1 -type f -print0 |
  sort -z | xargs -0 sha256sum > "$artifacts/source-inputs.sha256"
rustc +1.95.0 --version > "$artifacts/toolchain.txt"
cargo +1.95.0 --version >> "$artifacts/toolchain.txt"
recheck() {
  local code=$?
  trap - EXIT
  # Recheck cannot turn the original failure into success.
  sha256sum -c "$artifacts/source-inputs.sha256" > "$artifacts/source-recheck.txt" || code=1
  # Inventory follows the final recheck on both success and ordinary failure.
  python3 -B -I "$workspace/ci/inventory.py" || code=1
  exit "$code"
}
trap recheck EXIT
python3 -B -I "$workspace/ci/test_controls.py" 2>&1 | tee "$artifacts/validator-controls.log"
python3 -B -I "$workspace/ci/verify_artifacts.py" --workspace "$workspace" --artifacts "$artifacts" --controls-only
bash "$workspace/ci/run.sh"
