#!/usr/bin/env bash
# Recheck the actual migration CLI, using only source files from the given local checkout.
set -euo pipefail
here=$(cd -- "$(dirname -- "$0")" && pwd)
repo=$(cd -- "${1:?usage: bash verify.sh /path/to/Proteus-desktop}" && pwd)
base=b6a7ec2d8d7e486c8aba01291aa8c89774c4cded
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
export TMPDIR="$scratch" PYTHONDONTWRITEBYTECODE=1
cd "$scratch"
git init -q
git -C "$repo" archive "$base" scripts/settings-migration.py scripts/test_settings_migration.py scripts/test_release_shortcut.py scripts/portable/install-shortcut scripts/portable/proteus-native | tar xf -
git add scripts
printf 'Desktop: %s\n' "$base"
python3 --version
git apply --check --index "$here/source.patch"
git apply --include=scripts/test_settings_migration.py "$here/source.patch"
run() { python3 -m unittest discover -v -s scripts -p 'test*.py'; }
if run >red.log 2>&1; then echo 'Baseline unexpectedly passed' >&2; exit 1; fi
grep -q '^FAILED (failures=2)' red.log
grep -q '^FAIL: test_restore_keeps_destination_window_state_' red.log
grep -q '^FAIL: test_invalid_local_preferences_abort_before_any_restore' red.log
if grep -q '^ERROR:' red.log; then cat red.log; exit 1; fi
sed -n -e '/^test_/p' -e '/^Ran /p' -e '/^FAILED /p' red.log
git apply --include=scripts/settings-migration.py "$here/source.patch"
git diff --check
git apply --reverse --check "$here/source.patch"
run
