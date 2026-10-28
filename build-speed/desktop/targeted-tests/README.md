# Targeted Desktop tests without unrelated extension builds

This is a proposed launcher-only patch for **Proteus-desktop
`f5c5c88a686b4b85c03734b6d83227ba65afb96b`**. It does not change the upstream
repository or the Desktop production source.

The pinned `scripts/test.py` always resolves and packages the external
extensions before invoking `cargo test --locked --workspace`, even when
the caller explicitly selected the headless `proteus-diff` or `proteus-tabs`.
Those two crates have only serde-family dependencies in this source snapshot.

## Proposed behavior

After applying the patch to the exact upstream source:

```sh
python3 scripts/test.py -p proteus-diff --lib
python3 scripts/test.py -p proteus-tabs --lib
python3 scripts/test.py -p proteus-diff -p proteus-tabs
```

These explicit package checks do not resolve, license-check or package the
unselected external extensions, and do not receive an injected `--workspace`.
Desktop's own license check, resource limiter, `--locked`, test-thread default,
caller environment and failure status remain intact.

**The default `python3 scripts/test.py` remains the full workspace gate, with
real external extensions.** A targeted pass is not aggregate qualification.
Native UI, extension integration, shared contracts, multi-crate behavior and
release changes still need the applicable full validation.

The fast path accepts only exact `-p NAME`, `-pNAME`, `--package NAME` or
`--package=NAME` selectors for the two audited crates; repeated selectors are
allowed. It recognizes a deliberately small set of non-selection options
(`--lib`, `--doc`, `--no-run`, `--no-fail-fast`, lock/offline flags,
verbosity, jobs, color and message format), one test filter and the libtest
`--` boundary. Any other option, mixed/non-headless package, wildcard,
workspace/all/exclude selector, manifest override or ambiguous syntax retains
the original full preparation path. Unsupported options are not silently
discarded. This conservative fallback can still be expensive.

## Lightweight verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 build-speed/desktop/targeted-tests/check.py
```

Requires only Python 3.11+ and Git. No Rust, npm, dependency download, upstream
checkout or product execution is performed. The verifier:

1. Verifies the saved upstream launcher against its pinned Git blob and size.
2. Verifies the patch hash, checks and applies it to a temporary text-only copy.
3. Verifies the resulting candidate hash.
4. Runs 15 Python regression controls against that reconstructed candidate,
   using fake subprocess, source-resolution, resource-limit and license-check
   modules. Tests cover explicit/mixed/malformed selectors, the libtest boundary,
   the unchanged default full command, license and build failures, exit status,
   caller settings and the resource-limiter hook.

`upstream/test.py` is a read-only fixture, not an executable test target.
The source identity is in `source-identity.json`; the only proposed upstream
change is `desktop-headless-test-selection.patch`.

The dedicated Actions workflow runs this same small check only for changes to
this delivery or its workflow on `ci/desktop-targeted-tests-20261028`.
There is no PR-trigger duplicate or Rust/native/portable build.

## Evidence limits

Local controls and exact patch application passed. They establish runner
command selection and fail-closed fallback, not real Cargo tests or performance.
Rust tests, external-extension integration, the Desktop workspace gate, UI and
portable validation are **not run** by this package. No elapsed-time speedup
has been measured or claimed. Existing historical pure-crate results apply to
their own pinned source revisions, not automatically to this newer commit.
