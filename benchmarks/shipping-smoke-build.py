"""Source-only shipping build adapter. No test runner, DCP or installer execution."""
import hashlib
import json
import os
import stat
from pathlib import Path

CORE = "1f533a13f20a93bf164f7c8a169553b0b219bb51"
TREES = {"baseline": "9a122670d8e4360e4cdccc930569f141629baefc",
         "candidate": "44021ca3f2cdf91046345460709a254f04299e52"}
MODULES = "f5336923bcd01e581e64c4fbe84fa7f13388f5a5"
CORE_INPUTS = {
    "Cargo.toml": "4a8dfea7f7d3438dd9883225c392f229d96a8d5d4291f8d7d64555dd1f99e0b3",
    ".cargo/config.toml": "02c7c1be9111eee46b3f3587f0d60dd10ce190a53acd317b28e67aa66c70f59a",
    "rust-toolchain.toml": "665af4518a36f5433ed82dd6557dc7870885bd5e676bd37e0eb9840c125ad513",
    "crates/proteus-core/Cargo.toml": "e9f491fff08cbbb07b26dde5675594e174dd89c9636b59093cd0c4a2c0952cb6",
    "crates/proteus-core/src/main.rs": "b607368a6da91e942cc5b49e57d2253af633bd85c30cb721ff1ca0a3558bdae8",
    "scripts/build_module.py": "a2b87bd1d3492809a2283d309c18b267d7a703a183a43c7aa522a3640591c487",
    "scripts/sources.py": "9894a103674ad078f013bc49250ebcd6cfdf96263332374473a06ce874929b58",
    "crates/proteus-core/src/process_memory.rs": "0b641cc80bca822e1e60bc2872cf551c82d3a47d9e0f6b2b53350f22aedd42b8",
    "crates/proteus-core/build.rs": "e9b59ffef6ca66127ccc9a1b2e4c6cb8c4c14349d791b1c4c28af3a6297359fb",
    "Cargo.lock": "185d8f8dbd046a56f1f1e0100c42a800857113d3436e73b86a42364e978c6e2f",
    "repositories.json": "a8f8bcb48c09787d376e413cec823329f880502b91875498b086c5f0c495f282"
}
REPLAY_LEAVES = {
    "crates/proteus-core/src/main.rs": "c0f5659f81baa63b59b294e33887d08c80039486",
    "crates/proteus-core/src/core/module_catalog.rs": "278cbdaf7851bb363c80ad9d590a2e36693886c9",
    "crates/proteus-core/src/core/module_catalog/components.rs": "ab2c70b4c00b6878682e708086996a5feedbfbf3",
    "crates/proteus-core/src/process_adapters/config.rs": "203c5cf3de73e1b9738eb5cdd7807c9c1036e03c",
    "crates/proteus-core/src/core/workflow_replay/mod.rs": "f93d648b155bea9f12a2f24c9ac15cc548cca438",
    "crates/proteus-core/src/core/workflow_replay/replay_runtime/adapters.rs": "895d803038ef5d7ac547089e528359a2aa5d63c5",
    "crates/proteus-core/src/core/config_snapshot.rs": "89ba08e5fb97dc72fc2cd90f3ff5c09fdcaa2a65",
    "crates/proteus-core/src/core/workflow_replay/report.rs": "b061ba317228fb96cb54182c481fc3cf28763f84"
}

REPLAY_LEAVES.update({
    "crates/proteus-core/src/cli_workflow_replay.rs": "e5bf5c27b64e21ec8a9b275dc59b64e4a929c492",
    "crates/proteus-core/src/core/workflow_replay/fixture.rs": "204ebfa4becf200b6007d7618a4dd5115abeb549",
    "crates/proteus-process-host/src/writer.rs": "2fc6b8451f1ccb1dac8bc6556ee09f358c20b21a",
    "crates/proteus-process-host/src/receive.rs": "125576e92365dac70afa7a2afe27a8a5ce409d6b",
    "crates/proteus-process-host/src/framing.rs": "16339a37981c2f115d4b988bb2782f8a3e8f4e9f",
    "crates/proteus-process-host/src/transport.rs": "fd295ec0f6fdc34c775e75806e2df01ecbd0b8f6",
    "crates/proteus-module-protocol/src/v3/config.rs": "e1aac4897ad75ae60a68b88767bcd74e71eee67e"
})


def prepare(f, args, root, evidence, env):
    """f is the exact hash-bound final qualifier module; only pure source helpers reused."""
    # support() is the admission-wired in-memory graph, never the legacy importer.
    h, recipe, foundation, compact = f.support(args)
    require_release_environment(env)
    final_raw = f.bounded(args.manifest, 128 * 1024)
    final = f.q.strict(final_raw)
    f.validate(h, final, compact)
    root, publication = Path(root), Path(args.publication).resolve()
    runner = h.Runner(evidence, root, 300)
    publication_head = runner.ok("publication-head", ["git", "rev-parse", "HEAD"], publication, env, 10).strip()
    if publication_head != "e3b3dccb608de9c978ba9f7eba69d3a066e5c8a3":
        raise RuntimeError("immutable publication checkout differs")
    prepared, snapshots = {}, {}
    class Labelled:
        def __init__(self, prefix):
            self.prefix = prefix
        def ok(self, label, *values):
            return runner.ok(self.prefix + "-" + label, *values)
    for arm in ("baseline", "candidate"):
        source = root / arm
        h.checkout(runner, arm + "-source", source, foundation["core"]["repository"], CORE, env)
        if arm == "baseline":
            files, identity = f.q.plan_all(h, Labelled(arm), source, env, publication, foundation)["production"]
        else:
            files, identity = f.c.plans(h, Labelled(arm), source, env, publication, compact, foundation)["production"]
            files = {path: raw.decode("utf-8") for path, raw in files.items()}
            if identity["tree"] != final["source_base_tree"]:
                raise RuntimeError("candidate compact base differs")
            for patch in final["patches"]:
                path = patch["source"]
                raw = files[path].encode() if path in files else h.source_bytes(source, path)
                if h.git_blob(raw) != patch["preimage_blob"] or h.sha(raw) != patch["preimage_sha256"]:
                    raise RuntimeError("final preimage mismatch")
                files[path] = raw.decode()
                h.apply_exact(files, f.q.verify_file(h, publication, patch), [])
                raw = files[path].encode()
                if h.git_blob(raw) != patch["postimage_blob"] or h.sha(raw) != patch["postimage_sha256"]:
                    raise RuntimeError("final postimage mismatch")
            flat = h.parse_tree(runner.ok("candidate-original-tree",
                ["git", "ls-tree", "-r", "-z", "--full-tree", "HEAD"], source, env, 30, 2*1024**2))
            amended = h.flat_with_files(flat, files)
            identity = {"tree": h.complete_tree(amended), "changed_blobs": {
                path: value["sha"] for path, value in amended.items()
                if value["sha"] != flat.get(path, {}).get("sha")}}
            if identity != final["plan"]:
                raise RuntimeError("candidate complete composition differs")
            files = {path: text.encode() for path, text in files.items()}
        if identity["tree"] != TREES[arm]:
            raise RuntimeError("wrong source arm")
        prepared[arm] = (source, files, identity)
    # Both full source trees were checked before either arm is materialized.
    for arm, (source, changed, identity) in prepared.items():
        h.materialize(runner, arm, source, changed, identity["tree"], env)
        snapshots[arm] = h.tracked_snapshot(runner, arm + "-before", source, env)
    modules = root / "modules"
    h.checkout(runner, "stock-modules", modules, foundation["fixture"]["repository"], MODULES, env)
    tree = runner.ok("modules-tree", ["git", "rev-parse", "HEAD^{tree}"], modules, env, 10).strip()
    if tree != foundation["fixture"]["tree"]:
        raise RuntimeError("stock Modules tree differs")
    for name, expected in foundation["fixture"]["source_sha256"].items():
        if h.file_sha(modules / name) != expected:
            raise RuntimeError("stock Modules source changed: " + name)
    snapshots["modules"] = h.tracked_snapshot(runner, "modules-before", modules, env)
    for arm, (source, _, _) in prepared.items():
        source_inputs(source, snapshots[arm], h)
        cargo_configuration(source, env, snapshots[arm])
    for name in (".cargo/config.toml", "rust-toolchain.toml"):
        if file_hash(modules / name) != CORE_INPUTS[name]:
            raise RuntimeError("stock Modules build configuration differs: " + name)
    cargo_configuration(modules, env, snapshots["modules"])
    clean_source_paths(modules, snapshots["modules"])
    return {"sources": {arm: str(value[0]) for arm, value in prepared.items()},
            "modules": str(modules), "snapshots": snapshots,
            "foundation": foundation, "source_trees": TREES, "stage_records": runner.records,
            "release_environment": env, "replay_source_leaves": REPLAY_LEAVES,
            "effective_profile": {"name": "release", "opt_level": "3", "debug": 0,
                "debug_assertions": False, "overflow_checks": False, "lto": False,
                "codegen_units": 16, "panic": "unwind", "incremental": False,
                "features": [], "target_rustflags": ["-C", "link-arg=-fuse-ld=lld"]}}


def build_core(primitives, supervisor, arm, prepared, target, env, output):
    require_release_environment(env, prepared["release_environment"])
    source = Path(prepared["sources"][arm])
    if Path(target).exists():
        raise RuntimeError("fresh target directory required")
    cargo_configuration(source, env, prepared["snapshots"][arm])
    clean_source_paths(source, prepared["snapshots"][arm])
    argv = primitives.shipping_build_argv(source, target)
    supervisor.command(argv, str(source), env, output, 1790, 12*1024**2)
    values = [primitives.strict(line) for line in (Path(output)/"stdout.raw").read_bytes().splitlines()]
    artifact = select_core_artifact(primitives, values, source, target)
    executable = artifact["executable"]
    clean_source_paths(source, prepared["snapshots"][arm])
    cargo_configuration(source, env, prepared["snapshots"][arm])
    receipt = executable_receipt(executable)
    return {**receipt, "cargo_artifact": artifact, "source_tree": TREES[arm],
            "argv": argv, "environment": env, "effective_profile": prepared["effective_profile"],
            "build_input_sha256": {name: prepared["snapshots"][arm][name] for name in CORE_INPUTS}}


def build_reference(f, h, primitives, supervisor, prepared, target, env, python, output):
    require_release_environment(env, prepared["release_environment"])
    source = Path(prepared["sources"]["baseline"])
    if Path(target).exists():
        raise RuntimeError("fresh reference target required")
    clean_source_paths(source, prepared["snapshots"]["baseline"])
    modules = Path(prepared["modules"])
    clean_source_paths(modules, prepared["snapshots"]["modules"])
    cargo_configuration(modules, env, prepared["snapshots"]["modules"])
    env = dict(env, PROTEUS_MODULES_SOURCE=str(modules))
    # Resolve the stock SDK graph before building; no Cargo patch or test environment.
    metadata_dir = Path(output).parent / "reference-metadata"
    supervisor.command(["cargo", "metadata", "--locked", "--format-version", "1",
                        "--manifest-path", str(modules / "Cargo.toml")],
                       str(modules), env, metadata_dir, 30, 4*1024**2)
    metadata = primitives.strict((metadata_dir / "stdout.raw").read_bytes())
    graph = f.q.stock_graph(h, metadata, prepared["foundation"])
    selected = [x for x in metadata["packages"] if x["name"] == "proteus-reference-module"]
    primitives.require(len(selected) == 1 and selected[0]["source"] is None
        and Path(selected[0]["manifest_path"]) == modules / "components/process-module/Cargo.toml",
        "foreign reference workspace target")
    argv = [python, "-B", "-S", str(source / "scripts/build_module.py"), "--profile", "release",
            "--target-dir", str(target)]
    supervisor.command(argv, str(source), env, output, 1790, 12*1024**2)
    raw = (Path(output) / "stdout.raw").read_text().strip()
    executable = Path(raw).resolve()
    primitives.require("\n" not in raw and executable == Path(target).resolve() /
                       "release/proteus-reference-module", "reference output identity")
    clean_source_paths(source, prepared["snapshots"]["baseline"])
    clean_source_paths(modules, prepared["snapshots"]["modules"])
    cargo_configuration(modules, env, prepared["snapshots"]["modules"])
    return {**executable_receipt(executable), "argv": argv, "environment": env,
            "source_tree": prepared["foundation"]["fixture"]["tree"],
            "stock_sdk_graph": graph, "effective_profile": prepared["effective_profile"],
            "compiler_artifact_observation": "SUPPORTED_SCRIPT_SOURCE_BOUND_NOT_SEPARATELY_REEMITTED",
            "build_script_sha256": CORE_INPUTS["scripts/build_module.py"],
            "resolver_sha256": CORE_INPUTS["scripts/sources.py"]}


def require_release_environment(env, expected=None):
    required = {"PATH", "HOME", "CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN",
                "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "CARGO_TERM_COLOR",
                "GIT_TERMINAL_PROMPT", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL",
                "PYTHONDONTWRITEBYTECODE", "PYTHONOPTIMIZE", "PYTHONHASHSEED", "LC_ALL", "TZ"}
    if set(env) != required or any(not isinstance(v, str) for v in env.values()):
        raise RuntimeError("release environment is not the exact fresh allowlist")
    if (env["RUSTUP_TOOLCHAIN"] != "1.95.0" or env["CARGO_BUILD_JOBS"] != "2"
            or env["CARGO_INCREMENTAL"] != "0" or env["PYTHONDONTWRITEBYTECODE"] != "1"
            or env["PYTHONOPTIMIZE"] != "0" or env["GIT_CONFIG_NOSYSTEM"] != "1"
            or env["GIT_CONFIG_GLOBAL"] != "/dev/null"
            or (expected is not None and env != expected)):
        raise RuntimeError("release settings differ")
    # In particular empty RUSTFLAGS/CARGO_ENCODED_RUSTFLAGS are NOT admitted.
    return env


def cargo_configuration(source, env, snapshot):
    source = Path(source)
    expected = source / ".cargo/config.toml"
    for root in (source, *source.parents, Path(env["CARGO_HOME"]), Path(env["HOME"])):
        for name in ("config", "config.toml"):
            path = root / name if root == Path(env["CARGO_HOME"]) else root / ".cargo" / name
            if path.exists() or path.is_symlink():
                if path != expected or file_hash(path) != snapshot[".cargo/config.toml"]:
                    raise RuntimeError("ambient or changed Cargo configuration: " + str(path))
    # Exact toolchain; no target/profile env, wrappers, linker/allocator env,
    # feature override or empty-rustflags masking exists.


def clean_source_paths(root, snapshot):
    root, found = Path(root), set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        if Path(directory) == root and ".git" in dirs:
            dirs.remove(".git")
        for name in dirs:
            if (Path(directory) / name).is_symlink():
                raise RuntimeError("indirect source directory")
        for name in names:
            path = Path(directory) / name
            relative = str(path.relative_to(root))
            if relative not in snapshot or file_hash(path) != snapshot[relative]:
                raise RuntimeError("source/import closure changed: " + relative)
            found.add(relative)
    if found != set(snapshot):
        raise RuntimeError("source/import closure missing tracked files")


def source_inputs(source, snapshot, h):
    if any(snapshot.get(name) != value or file_hash(Path(source) / name) != value
           for name, value in CORE_INPUTS.items()):
        raise RuntimeError("shipping main/allocator/profile/lock/config/build input changed")
    for name, blob in REPLAY_LEAVES.items():
        if h.git_blob(h.source_bytes(source, name)) != blob:
            raise RuntimeError("replay substitution source leaf differs: " + name)
    clean_source_paths(source, snapshot)



def open_regular_nofollow(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("nonabsolute/traversing input")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = following
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)

def file_receipt(path, cap=512*1024**2):
    path = Path(path)
    if not path.is_absolute() or str(path.resolve()) != str(path):
        raise RuntimeError("noncanonical input path")
    fd = open_regular_nofollow(path)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 <= before.st_size <= cap:
            raise RuntimeError("nonregular/oversized input")
        digest, count = hashlib.sha256(), 0
        while True:
            chunk = os.read(fd, min(65536, cap + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > cap:
                raise RuntimeError("input grew beyond cap")
            digest.update(chunk)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in fields) or count != before.st_size:
            raise RuntimeError("input changed during read")
        return {"path": str(path), "bytes": count, "sha256": digest.hexdigest(),
                "device": before.st_dev, "inode": before.st_ino,
                "mode": stat.S_IMODE(before.st_mode), "uid": before.st_uid,
                "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns}
    finally:
        os.close(fd)


def executable_receipt(path):
    receipt = file_receipt(path)
    if not receipt["mode"] & 0o111 or not receipt["bytes"]:
        raise RuntimeError("nonexecutable shipping artifact")
    return receipt


def file_hash(path):
    return file_receipt(path)["sha256"]


def select_core_artifact(primitives, values, source, target):
    """Pure selector: expected source and target are canonical absolute paths."""
    rows, finished = [], []
    for value in values:
        if value.get("reason") == "build-finished":
            finished.append(value)
        item = value.get("target", {})
        if value.get("reason") == "compiler-artifact" and value.get("executable") and item.get("name") == "proteus":
            profile = value["profile"]
            executable = Path(value["executable"])
            primitives.require(item["kind"] == ["bin"] and item["src_path"] ==
                str(source / "crates/proteus-core/src/main.rs") and value["features"] == []
                and profile["test"] is False and profile["opt_level"] == "3"
                and profile["debug_assertions"] is False and profile["overflow_checks"] is False
                and profile["debuginfo"] == 0 and type(profile["debuginfo"]) is int
                and value["fresh"] is False
                and executable == Path(target) / "release/proteus",
                "not exact ordinary shipping release artifact")
            package = value["package_id"]
            primitives.require(package in {"path+" + (source / "crates/proteus-core").as_uri() +
                "#0.1.0-alpha.3", "path+" + (source / "crates/proteus-core").as_uri() +
                "#proteus-core@0.1.0-alpha.3"}, "foreign Cargo package")
            rows.append(value)
    primitives.require(len(rows) == 1 and len(finished) == 1 and
                       finished[0].get("success") is True, "shipping artifact/finish missing or ambiguous")
    return rows[0]
