# Desktop --reuse-hosts: test-only candidate

Target: Proteus-harness/Proteus-desktop commit
e9ca11aab25f6d3a8d09b79c8c5266c1320af2b6.

`reuse-hosts-controls.patch` adds only
`scripts/test_release_reuse_hosts.py`. No production source, profile, package
selection, release rule or documentation is changed.

## Checked

12 newly authored stdlib controls passed under a process/network audit guard:

- No host Cargo call; reuse Core/Desktop files while requesting module and
  extension packaging without `--no-build`.
- Release, fast, debug and no-archive profiles/flags retain current semantics.
- Existing host paths use per-checkout relative or shared absolute target dirs.
- Missing Core or Desktop binary fails before assembly or package requests.
- Provenance identifies reused hosts and hashes copied binaries; the existing
  release-assets gate rejects it as a clean pinned release.
- Combined reuse flags preserve current reuse-binaries precedence; fast/debug
  remain mutually exclusive.

Only inert temporary files are copied. All subprocess dependencies are fake;
source resolution, resource limiting, hook assembly and metadata dependencies
are replaced before importing the reviewed source. The existing release-assets
comparison is exercised with source checks stubbed and destructive/export
operations patched. The guard rejects standard process/network audit events and
checks its own activation with synthetic events.

The 4 reviewed source files in `snapshot/` match Git blob IDs recorded in
`source-identity.json`. The new test is not represented as upstream source.
The patch passed `git apply --check --whitespace=error-all`; applying it in an
empty temporary directory reproduced the test file exactly.

Recheck locally:

    PYTHONDONTWRITEBYTECODE=1 python3 validate_guarded.py

`validation.json` and `validation.log` record the guarded run.

## Limits

These checks prove launcher wiring with fakes, not successful real package
builds, executable compatibility, native UI, runtime performance or portable
end-to-end behavior. No Cargo/native compilation, product execution, clone,
existing test suite, upstream write or publication was performed.

The separate release-version check against the excluded aggregate manifest
and stale documentation remain findings, not part of this candidate.
