# Independent pre-run review

Source review permits the proposed bounded four-test command-construction check. No tests or project modules were executed during this review.

Independently verified candidate adapters.py SHA256 `82de52c4e21b3f5c9c43e050f16d32fca8de30b3e746d84ab39de373f2dd6a8e` and binary_identity_test.py SHA256 `1f860405fc3f2e33d6552d639e6fa559083b7b71b530d8f51fa9ba1b5e0eefa4`. Comparing the candidate against the previously catalogued current Core adapter shows exactly the one argv[0] replacement. The default basename retains its exact command; renamed and Unicode/space basenames select the normalized target name as one argv element, rather than the unrelated hardcoded sibling.

The four test bodies call actual adapters.prepare with an owned temporary config/case and plain fixture bytes. CORE, load_module and copy_auth are patched before invocation. The selected non-Go, non-Pi profile follows the local synthetic config branch; native loading and auth copying are replaced rather than executed. The inspected module imports are standard library and declarations. Tests neither import runner nor launch an evaluated binary or server. They verify unchanged selected path/bytes and every remaining argv token. The sibling fixture strengthens name discrimination but is not an executed-executable identity proof.

For the proposed fresh -I -B -S baseline/candidate test processes, insert only the exact copied harness directory and record/verify imported adapters and test-module __file__ paths plus source hashes; this avoids mistaking an unrelated same-name module for the reviewed copy. Keep HOME/TMPDIR owned and preserve before/after copy digests. A baseline default-name pass and three renamed-name assertion failures would be expected; candidate four passes remain unobserved at this stage. Run only this target, not other project discovery or the benchmark runner.

Limits: no actual executable, mount, provider, API, auth, historical benchmark or runner integration coverage. The normalized path producer already resolves symlinks, so this fix targets resolved basename identity rather than preserving a user's original symlink spelling. No broader execution or isolation guarantee follows from this review.

## Driver addendum

Read run_target.py and both runtime expected-hash JSON files without executing them. Driver SHA256 verified as `1e64b5d54b30ef648bd9e93241232bc9fe3bbdfbb5d4fd6d74bbccd5acd3e685`. Baseline adapter expected hash `e4fa936b9228b54333607c4f9e28cd989333beacd6e5b989ac5f3ea3054ee247` matches the previously catalogued source; candidate and test hashes match the reviewed revision. Driver checks both files before import and after tests, verifies both module paths, selects only PreparedBinaryIdentity and requires exactly four cases. No blocker for the two specified isolated-mode Python target invocations. Results, assertion identities and unchanged files still require post-run inspection; no execution occurred in this review.
