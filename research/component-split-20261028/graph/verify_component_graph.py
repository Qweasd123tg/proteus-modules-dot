"""Read-only, source-bound dependency inspection; does not invoke Cargo.

This proves declared local normal/build graph isolation only, not compilation,
linking, changed-unit freshness, RPC conformance, or performance.
"""
import hashlib
import json
from pathlib import Path
import sys
import tomllib

HERE = Path(__file__).resolve().parent
SNAPSHOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/workspace/scratch/3ba0fff8d310/proteus-component-split-20261028")
CANDIDATE = SNAPSHOT / "candidate"
UPSTREAM = SNAPSHOT / "upstream"
EVIDENCE = HERE / "evidence"
CORE_REV = "1f533a13f20a93bf164f7c8a169553b0b219bb51"
CORE_URL = "https://github.com/Proteus-harness/Proteus-core.git"


def read(path):
    return tomllib.loads(path.read_text())


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


identities = json.loads((EVIDENCE / "identities.json").read_text())
for identity in identities:
    assert git_blob((EVIDENCE / identity["path"]).read_bytes()) == identity["blob_sha"], identity

candidate_root = read(CANDIDATE / "Cargo.toml")
upstream_root = read(UPSTREAM / "Cargo.toml")
assert candidate_root.get("profile", {}) == upstream_root.get("profile", {}), "profile changed"
assert candidate_root["workspace"]["dependencies"] == upstream_root["workspace"]["dependencies"], "pins changed"
assert set(candidate_root["workspace"]["members"]) - set(upstream_root["workspace"]["members"]) == {
    "components/plan-module", "components/tool-adapter"}, "unexpected workspace addition"
assert set(upstream_root["workspace"]["members"]) <= set(candidate_root["workspace"]["members"]), "removed workspace member"

paths = {
    "proteus-plan-module": CANDIDATE / "components/plan-module/Cargo.toml",
    "proteus-tool-adapter": CANDIDATE / "components/tool-adapter/Cargo.toml",
    "plan-tool": EVIDENCE / "modules/tool/plan-tool/Cargo.toml",
}
for name in ("proteus-contracts", "proteus-module-sdk", "proteus-module-protocol", "proteus-process-host"):
    paths[name] = EVIDENCE / "core/crates" / name / "Cargo.toml"
manifests = {name: read(path) for name, path in paths.items()}
assert all(manifests[name]["package"]["name"] == name for name in manifests)
for name in ("proteus-plan-module", "proteus-tool-adapter"):
    assert not manifests[name].get("dev-dependencies"), f"unexpected dev deps in {name}"
assert manifests["proteus-plan-module"].get("bin") == [{"name": "proteus-plan-module", "path": "src/main.rs"}]

conceptual_paths = dict(paths)
conceptual_paths["plan-tool"] = CANDIDATE / "tool/plan-tool/Cargo.toml"


def dependencies(manifest):
    for kind in ("dependencies", "build-dependencies"):
        yield from ((kind, name, spec) for name, spec in manifest.get(kind, {}).items())
    # Union all target cfgs conservatively: no desired platform can hide an edge.
    for target in manifest.get("target", {}).values():
        for kind in ("dependencies", "build-dependencies"):
            yield from ((kind, name, spec) for name, spec in target.get(kind, {}).items())


graph = {}
pending = ["proteus-plan-module"]
seen = set()
while pending:
    name = pending.pop()
    if name in seen:
        continue
    seen.add(name)
    graph[name] = []
    for kind, alias, original in dependencies(manifests[name]):
        spec = original if isinstance(original, dict) else {"version": original}
        if spec.get("workspace"):
            spec = candidate_root["workspace"]["dependencies"][alias]
            spec = spec if isinstance(spec, dict) else {"version": spec}
        dependency = spec.get("package", alias)
        graph[name].append({"package": dependency, "kind": kind})
        if "path" in spec:
            assert dependency in paths, f"unreviewed local dependency: {name}->{dependency}"
            actual = (conceptual_paths[name].parent / spec["path"] / "Cargo.toml").resolve()
            expected = conceptual_paths[dependency].resolve()
            assert actual == expected, f"path identity mismatch: {name}->{dependency}: {actual} != {expected}"
        elif "git" in spec:
            assert dependency in paths, f"unreviewed git dependency: {name}->{dependency}"
            assert spec["git"] == CORE_URL and spec.get("rev") == CORE_REV, "unexpected Git pin"
        elif dependency in paths:
            raise AssertionError(f"internal package unexpectedly comes from registry: {name}->{dependency}")
        if dependency in paths:
            pending.append(dependency)

assert seen == set(paths), f"unexpected declared internal closure: {seen}"
for forbidden in ("proteus-reference-module", "proteus-core", "proteus-desktop",
                  "file-tools", "git-tools", "shell-tool", "model-pack", "coding-workflow"):
    assert all(edge["package"] != forbidden for edges in graph.values() for edge in edges), forbidden

upstream_lock = read(UPSTREAM / "Cargo.lock")
candidate_lock = read(CANDIDATE / "Cargo.lock")
def key(package):
    return package["name"], package["version"], package.get("source")
before = {key(package): package for package in upstream_lock["package"]}
after = {key(package): package for package in candidate_lock["package"]}
added = set(after) - set(before)
assert added == {("proteus-plan-module", "0.1.0-alpha.3", None),
                 ("proteus-tool-adapter", "0.1.0-alpha.3", None)}, f"lock additions: {added}"
assert not set(before) - set(after), "existing lock packages removed"
for identity, previous in before.items():
    current = after[identity]
    if identity[0] == "proteus-reference-module":
        expected = dict(previous)
        expected["dependencies"] = sorted([*previous["dependencies"], "proteus-tool-adapter"])
        assert current == expected, "reference lock edge mismatch"
    else:
        assert current == previous, f"unrelated lock entry changed: {identity}"
for name in ("proteus-plan-module", "proteus-tool-adapter"):
    locked = after[(name, "0.1.0-alpha.3", None)]
    expected = sorted(edge["package"] for edge in graph[name])
    assert sorted(locked.get("dependencies", [])) == expected, f"new lock edge mismatch: {name}"

report = {
    "status": "PASS: static declared normal/build graph and lock delta only",
    "executed_cargo": False,
    "executed_product": False,
    "compiled_or_measured": False,
    "declared_internal_closure": sorted(seen),
    "graph": graph,
    "profile": candidate_root.get("profile", {}),
    "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in [*paths.values(), CANDIDATE / "Cargo.toml", CANDIDATE / "Cargo.lock"]},
}
print(json.dumps(report, indent=2))
