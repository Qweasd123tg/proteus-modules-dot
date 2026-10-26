#!/usr/bin/env bash
# Dedicated hosted job; any failed stage stops all later runtime work.
set -euo pipefail
repo=${GITHUB_WORKSPACE:?}
out=${STRICT_RESULTS_DIR:?}
targets=${STRICT_TARGET_ROOT:?}
official=${STRICT_OFFICIAL_DIR:?}
host="$repo/integration/strict-host"
fixture="$repo/integration/strict-host-fixture"
strict="$repo/experiments/strict-pair"
ci="$repo/ci/strict-fullturn"
mkdir "$out" "$targets"
export PYTHONDONTWRITEBYTECODE=1
export CARGO_INCREMENTAL=0 CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0
export CARGO_TERM_COLOR=never GIT_TERMINAL_PROMPT=0
run() {
  local name=$1; shift
  printf '%s\n' "$name" >> "$out/stage-started.txt"
  printf '%q ' "$@" > "$out/$name.command"; printf '\n' >> "$out/$name.command"
  "$@" > "$out/$name.log" 2>&1
  printf '%s\n' "$name" >> "$out/stage-passed.txt"
}
verify() { python3 -B -I "$ci/verify_ci.py" "$1" --repo "$repo" --output "$2" "${@:3}"; }
finish() {
  status=$?
  if ! verify source "$out/source-after.json"; then
    printf '%s\n' 'source recheck failed; no acceptance' > "$out/SOURCE-RECHECK-FAILED.txt"
    status=1
  fi
  printf '%s\n' "$status" > "$out/stage-exit-code.txt"
  exit "$status"
}
trap finish EXIT
verify source "$out/source-before.json"
git -C "$repo" rev-parse HEAD HEAD^{tree} > "$out/checkout-identity.txt"
printf '%s\n' "$GITHUB_SHA" "$GITHUB_REF" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT" > "$out/github-identity.txt"
run envelope-controls python3 -B -I "$ci/test_envelope.py" -v
verify tests "$out/envelope-controls.log" --kind envelope
run prerequisite-controls python3 -B -I "$ci/test_verify_ci.py" -v
verify tests "$out/prerequisite-controls.log" --kind prerequisite
run mock-controls python3 -B -I "$host/test_controller_mock.py" "$out/mock-controls" -v
verify tests "$out/mock-controls.log" --kind mock
run artifact-controls python3 -B -I "$host/tests_py/test_artifact_gate.py" --package "$host" -v
verify tests "$out/artifact-controls.log" --kind artifact
# Actual Linux /proc/pidfd/subreaper controls BEFORE toolchain, Cargo or Core.
run live-controls python3 -B -I "$host/test_controller.py" "$out/live-controls" -v
verify tests "$out/live-controls.log" --kind live
verify live "$out/live-controls"
run toolchain rustup toolchain install 1.95.0 --profile minimal --component rustfmt --no-self-update
export RUSTUP_TOOLCHAIN=1.95.0
run compiler rustc -Vv
run cargo-version cargo -V
run linker ld.lld --version
run official-init git -c core.hooksPath=/dev/null init "$official"
run official-fetch git -C "$official" -c core.hooksPath=/dev/null fetch --depth 1 https://github.com/Proteus-harness/Proteus-modules.git 7fceaebc3bed8add9b0e3091110f59deca86ba46
run official-checkout git -C "$official" -c core.hooksPath=/dev/null checkout --detach FETCH_HEAD
test "$(git -C "$official" rev-parse HEAD)" = 7fceaebc3bed8add9b0e3091110f59deca86ba46
git -C "$official" rev-parse HEAD HEAD^{tree} > "$out/official-identity.txt"
printf '%s\n' 'CARGO_INCREMENTAL=0' 'CARGO_PROFILE_DEV_DEBUG=0' 'CARGO_PROFILE_TEST_DEBUG=0' '-j2' 'separate target dirs: host official strict' > "$out/build-profile.txt"
printf '%s  %s\n' e9b46590a2ff92ded4f0934a540bbdd0e9aee83c7ebad0ac6c3bd5089b4a0848 "$official/Cargo.lock" | sha256sum -c - > "$out/official-lock-before.txt"
for graph in host fixture strict official; do
  case "$graph" in host) dir=$host;; fixture) dir=$fixture;; strict) dir=$strict;; official) dir=$official;; esac
  (cd "$dir"; run "fetch-$graph" cargo fetch --locked)
  (cd "$dir"; cargo metadata --locked --offline --format-version 1 > "$out/metadata-$graph.json" 2> "$out/metadata-$graph.stderr")
done
verify graphs "$out" --official "$official" > "$out/graph-gate.json"
export CARGO_TARGET_DIR="$targets/host"
(cd "$fixture"; run fixture-tests cargo test --locked --offline -j2 --test fixture -- --test-threads=1)
verify tests "$out/fixture-tests.log" --kind fixture
(cd "$fixture"; run fixture-build cargo build --locked --offline -j2 --bin proteus-strict-host-fixture)
(cd "$host"; run host-build cargo build --locked --offline -j2 --bin proteus-strict-agent-host)
export CARGO_TARGET_DIR="$targets/official"
(cd "$official"; run official-build cargo build --locked --offline -j2 -p proteus-reference-module --bin proteus-reference-module)
export CARGO_TARGET_DIR="$targets/strict"
(cd "$strict"; run strict-build cargo build --locked --offline -j2 --bin proteus-example-json-contracts-strict --bin proteus-example-hermes-verify-evidence-strict --example strict_json_policy)
run compiled-policy "$targets/strict/debug/examples/strict_json_policy" < "$host/fixtures/suite.json"
cp "$out/compiled-policy.log" "$out/policy.json"
verify policy "$out/policy.json"
args=(--host "$targets/host/debug/proteus-strict-agent-host" --official "$targets/official/debug/proteus-reference-module" --fixture "$targets/host/debug/proteus-strict-host-fixture" --producer "$targets/strict/debug/proteus-example-json-contracts-strict" --gate "$targets/strict/debug/proteus-example-hermes-verify-evidence-strict" --policy "$out/policy.json")
# Matching diagnostic is retained separately. No later stage after its failure.
run matching-diagnostic python3 -B -I "$host/run_host.py" "${args[@]}" --output "$out/diagnostic" --stage matching
run full-capture python3 -B -I "$host/run_host.py" "${args[@]}" --output "$out/full" --stage all
run full-semantic-gate python3 -B -I "$host/verify_host.py" --directory "$out/full" --package "$host"
verify source "$out/source-after.json"
cmp "$out/source-before.json" "$out/source-after.json"
git -C "$official" diff --exit-code > "$out/official-diff-after.txt"
verify graphs "$out" --official "$official" > "$out/graph-gate-after.json"
printf '%s\n' 'complete: 5 live controls, 16 fixture Rust tests, 7 turns + 1 direct admission case' > "$out/COMPLETE.txt"
