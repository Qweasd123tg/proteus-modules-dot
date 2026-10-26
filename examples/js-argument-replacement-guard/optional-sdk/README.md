# Optional known-SDK probe — adapted and unrun

Pure helper use does not require this directory. This optional probe uses only authored Python stdlib code, a trusted installed Node runtime, and a separately provisioned exact public Proteus SDK source. It does not download/vendor SDK code, call providers, run user hooks or spawn descendants in the authored fixtures.

## Prerequisites

- POSIX environment supporting nonblocking pipes/selectors, Python3, a trusted Node runtime, and at least1GiB +2MiB free on the package/output filesystem. No cleanup is attempted when reserve is insufficient.
- A trusted local SDK directory containing worker.mjs/hooks.mjs/ports.mjs/command.mjs/validation.mjs with the fixed hashes in probe.py. These match [Core commit1fc3ef223d10322815dd9290a50d045bc95402bb](https://github.com/Proteus-harness/Proteus-core/tree/1fc3ef223d10322815dd9290a50d045bc95402bb/examples/modules/hook-process). Obtain sources through your own approved process; this example never fetches them. Each selected SDK member must be a regular nonsymlink file: a symlinked worker can change Node's relative-import base ([Node24.19 ESM resolution algorithm](https://nodejs.org/download/release/v24.19.0/docs/api/esm.html#resolution-algorithm-specification)). The directory is resolved explicitly. This is a trusted, stable-filesystem requirement; pre/post hashes do not close concurrent replacement/TOCTOU races.
- Independently review this package and its CODE.sha256 digest, and the chosen Node executable's SHA-256. A hash supplied from the same untrusted source is not authenticity or execution permission. The flag below is deliberate-use friction, not an authorization verifier.

From the package root, using absolute caller-owned paths and trusted expected digests:

```sh
python3 -I -B -S optional-sdk/probe.py   --run-reviewed   --output results-local   --source-manifest-sha256 REVIEWED_PACKAGE_MANIFEST_SHA256   --node /absolute/path/to/trusted/node   --node-sha256 EXPECTED_NODE_BINARY_SHA256   --sdk-dir /absolute/path/to/trusted/core/examples/modules/hook-process
```

No shell, provider, network, command helper or host callback is invoked by the authored entry. Normal module loading reads local sources. The probe itself runs exactly two sequential direct Node children: all38 pure controls must pass and reap cleanly before one worker initializes four exports and handles13 sequential authored calls. The fixture has deliberate computed-safe and unguarded-later limitation modes; it is not a production policy hook.

A fresh `optional-sdk/results-local` leaf is required. The package manifest, all15 packaged source files, Node and five SDK files are hashed before/after. Outputs retain exact original request/response bytes and a strict Python integer/type oracle result. Four refusals must be exact -32000/unsafe_integer with data absent, not null; safe42 must succeed immediately after a refusal. Two Continue and seven replacements must match exactly, including the two accepted limitations. No callbacks or extra frames are permitted.

Limits:30s shared active deadline,10s pure read,3s per SDK exchange inside the total; at most6s explicit direct-child cleanup waits after the active deadline. Filesystem I/O/scheduling are not hard-preempted. Per-worker stdout64KiB/stderr16KiB, frame8KiB, requests4KiB, total stdin32KiB, aggregate retained content256KiB. Hashing/minimal environment are not a sandbox. Cleanup proves only recorded direct-child outcomes, not arbitrary descendant settlement. Budget failure can leave partial raw prefixes without final receipts; that is failure, never acceptance.

**Privacy:** raw initialization/call frames contain local fixture/cwd paths. Review/redact any artifacts before sharing them; no raw historical execution data is bundled in this package.

## Retest obligations for this adapted layout

Nothing in this assembled package has been executed. Before marking a delivery validated:

1. Inspect and verify the complete15-file CODE inventory and PACKAGE_MAP. No source must change during tests.
2. Run `python3 -I -B -S optional-sdk/test_oracle.py`: exactly18 named synthetic oracle controls, zero skipped/failed. Run `python3 -I -B -S optional-sdk/test_controller.py -v`: exactly9 named lifecycle mocks, zero skipped/failed. These are not Node or SDK behavior cases.
3. Review/test the **new path/configuration seam**: missing/relative runtime or SDK paths, mismatched Node hash, mismatched SDK file hash, symlink/nonregular selected SDK member and modified package source must fail before child execution; pair each with a valid provisioned-path control. These adaptations were not covered by the historical runtime.
4. Execute the bounded probe once on the intended provisioned runtime only after its prerequisites/resource supervision are accepted. Require38 exact pure names,14 exact SDK exchanges, all22 selected pre/post input identities, two clean exits0 and empty stderr. Reject partial evidence or unknown cleanup rather than retry automatically.
5. Independently read the retained raw protocol bytes with exact integer types and verify the specific outcomes/limits, not only the producer's status field. Keep Core/policy and all-platform claims out of the result.

This directory adds no workflow, remote branch, publication action or source-download command.
