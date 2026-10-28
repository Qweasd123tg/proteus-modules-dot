"""Private shipping release smoke entrypoint. Source-only; execution seal is unset.
Bootstrap trust: execute this reviewed file with its pinned CPython -I -B -S.
No downloaded top-level source executes before complete admission.
"""
import hashlib
import importlib.util
import json
import math
import os
import shutil
import signal
import stat
import sys
import time
import types
from pathlib import Path

AUTHORIZATION_SHA256 = "949b67b53c779c13fde88029a4a54d65cf8796a268a768e4bda868ce1948c8f1"
PLAN_SHA = "04d31854f46bc899e4093c05d8e65fc1a01e746515eeb479ffcf1536a5162d51"
FINAL_PASS = "465cb07666aa03567f3dee7a60367f607e5a4c58b4e04160f328e168e4539d65"
BASELINE_PASS = "5e6aca6e05c37775c7c847f23c9241e0ae7a1466668e84fc02ab32cf8003a339"
TREES = {"baseline": "9a122670d8e4360e4cdccc930569f141629baefc",
         "candidate": "44021ca3f2cdf91046345460709a254f04299e52"}
MODULE_KEYS = {"capture", "profile", "primitives", "semantics", "seed",
               "supervisor", "build", "dispatch"}
SUPPORT_PINS = {
    "final_helper": ("fde1ecccc4c8b204332796265db115eac4a52652593ecf371b7938e07645664e", 30192),
    "manifest": ("57e8026da965c49a4d4c83b40fb50398c64e358b7c16dc58c107c870051cf976", 41312),
    "compact_controller": ("33c8ec75122e71db5d034410144bac273a4606dbda59ac8e63a205905bcc2c8d", 41666),
    "compact_manifest": ("84e01c0e60b8936054cd1f6e91b7a1bc2bc500b7583160953e1976e9e1e75622", 51150),
    "qualified_controller": ("4cf85d5124f7d39cb38a3444287bf43254d74f1053a70fee926c6515ca3c6b3b", 78616),
    "qualified_manifest": ("dca653f3eda6ece4e9f339f531669a14e249e7a0cf151dd77a58b9fea5eef603", 117631),
    # PR35 is a separately materialized immutable input, NOT a newer-checkout path.
    "helper": ("2f917a4ca4dc71a3dfa8cf2dc376991a7ddf1580cd347aaff8cb6ccc50568147", 109703),
    "recipe": ("0a6b5a4aba9112abe866fa5131d7f0f58a771f3542ec891af51f96d9bd7dae82", 23264),
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def reject(value):
        raise RuntimeError("nonfinite JSON constant: " + value)
    def number(value):
        parsed = float(value)
        require(math.isfinite(parsed), "nonfinite JSON number")
        return parsed
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject, parse_float=number)



def open_regular_nofollow(path):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "nonabsolute/traversing input")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = following
        return os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)

def regular(path, cap):
    path = Path(path)
    require(path.is_absolute() and str(path.resolve()) == str(path), "noncanonical input path")
    fd = open_regular_nofollow(path)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= cap,
                "nonregular or oversized admission input")
        parts, count = [], 0
        while True:
            piece = os.read(fd, min(65536, cap + 1 - count))
            if not piece:
                break
            count += len(piece)
            require(count <= cap, "admission input grew")
            parts.append(piece)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        require(count == before.st_size and
                all(getattr(before, key) == getattr(after, key) for key in fields),
                "admission input changed during read")
        return b"".join(parts)
    finally:
        os.close(fd)


def hash_file(path):
    # Boot inputs are bounded; compiled artifacts use build.file_hash streaming.
    return hashlib.sha256(regular(path, 4*1024**2)).hexdigest()


def hex_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def admit_maps(bindings, authorization):
    require(set(bindings["module_paths"]) == MODULE_KEYS and
            set(bindings["module_hashes"]) == MODULE_KEYS and
            set(authorization["reviewed_module_hashes"]) == MODULE_KEYS,
            "unexpected or missing wrapper module BEFORE import")
    require(bindings["module_hashes"] == authorization["reviewed_module_hashes"] and
            all(hex_sha(value) for value in bindings["module_hashes"].values()),
            "wrapper source map differs")
    require(set(bindings["support_arguments"]) == set(SUPPORT_PINS) - {"final_helper"},
            "unexpected support input")
    paths = list(bindings["module_paths"].values()) + list(bindings["support_arguments"].values())
    paths += [bindings["final_helper"], bindings["model_fixture"]]
    require(all(isinstance(path, str) and Path(path).is_absolute() for path in paths) and
            len(paths) == len(set(paths)), "aliased or relative import inputs")


def relative_reference(roots, reference):
    require(type(reference) is dict and set(reference) == {"root", "path"}
            and reference["root"] in roots and type(reference["path"]) is str,
            "declared relative reference")
    pieces = reference["path"].split("/")
    require(pieces and all(piece not in ("", ".", "..") for piece in pieces)
            and not Path(reference["path"]).is_absolute(), "relative source traversal")
    return str(Path(roots[reference["root"]]).joinpath(*pieces))


def resolve_binding_template(template, entry_path):
    require(type(template) is dict and template["schema"] == 2
            and template["python"] == "OBSERVED_SYSTEM_CPYTHON"
            and template["rustup_home"] == "OBSERVED_RUSTUP_HOME"
            and template["path"] == "PINNED_RUST_TOOLCHAIN_AND_SYSTEM_PATH"
            and template["publication"] == "publication", "relative binding template")
    wrapper = Path(entry_path).resolve().parent.parent
    require(Path(entry_path).resolve() == wrapper/"benchmarks/shipping-smoke-entry.py",
            "entry checkout layout")
    roots = {"wrapper": str(wrapper), "publication": str(wrapper.parent/"qualification-source"),
             "pr35": str(wrapper.parent/"pr35-source")}
    require(all(Path(root).is_dir() and str(Path(root).resolve()) == root
                for root in roots.values()), "canonical declared checkout roots")
    resolved = dict(template)
    for key in ("module_paths", "support_arguments"):
        resolved[key] = {name: relative_reference(roots, ref) for name,ref in template[key].items()}
    for key in ("final_helper", "model_fixture", "host_policy", "final_pass_receipt",
                "baseline_qualification_receipt"):
        resolved[key] = relative_reference(roots, template[key])
    rustup = os.environ.get("RUSTUP_HOME", "")
    require(rustup and Path(rustup).is_absolute() and str(Path(rustup).resolve()) == rustup
            and Path(rustup).is_dir(), "canonical observed RUSTUP_HOME")
    toolchain = Path(rustup)/"toolchains/1.95.0-x86_64-unknown-linux-gnu"
    require(toolchain.is_dir() and str(toolchain.resolve()) == str(toolchain),
            "exact installed Rust toolchain directory")
    python = str(Path(sys.executable).resolve())
    require(sys.implementation.name == "cpython" and sys.version_info[:2] == (3,10)
            and sys.base_prefix == "/usr" and python.startswith("/usr/bin/python3."),
            "standard Ubuntu 22.04 isolated CPython")
    resolved.update(python=python, rustup_home=rustup, publication=roots["publication"],
                    path=str(toolchain/"bin")+":/usr/bin:/bin")
    return resolved, {"schema": 1, "roots": roots, "python": python,
                      "rustup_home": rustup, "rust_toolchain": str(toolchain),
                      "path": resolved["path"]}


def resolve_host_template(template, bindings, resolution):
    require(type(template) is dict and set(template) == {"schema", "python", "import_paths",
            "tools", "compiler_support", "python_imports", "support_files", "execution_context", "declared_toolchain"}
            and template["schema"] == 3 and template["python"] == "OBSERVED_SYSTEM_CPYTHON"
            and template["import_paths"] == "OBSERVED_ISOLATED_SYSTEM_SYS_PATH"
            and template["tools"] == ["cargo","rustc","git","cc","ld.lld","ar","ranlib","as","ld","clang","pkg-config","python"]
            and template["compiler_support"] == ["RUST_DRIVER_LLVM_SHALLOW", "CURRENT_GCC_HELPERS"]
            and template["python_imports"] == HOST_STDLIB
            and template["support_files"] == ["/etc/ld.so.cache", "/usr/lib/x86_64-linux-gnu/libc.so"],
            "declared host selector policy")
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode
            and not sys.flags.optimize and all(path and Path(path).is_absolute()
                and ".." not in Path(path).parts and path.startswith("/usr/lib/python3")
                for path in sys.path), "system isolated import roots")
    present, absent = [], []
    for path in sys.path:
        (present if os.path.lexists(path) else absent).append(path)
    require(all(Path(path).is_dir() and str(Path(path).resolve()) == path for path in present),
            "canonical existing stdlib roots")
    tools = {}
    for name in template["tools"]:
        path = bindings["python"] if name == "python" else shutil.which(name, path=bindings["path"])
        require(path, "missing declared host tool: "+name)
        tools[name] = path
    policy = {"schema": 2, "python": bindings["python"], "python_import_roots": present,
              "absent_import_paths": absent, "tools": tools,
              "rust_library_root": str(Path(resolution["rust_toolchain"])/"lib"),
              "python_imports": HOST_STDLIB,
              "support_files": template["support_files"],
              "execution_context": template["execution_context"],
              "declared_toolchain": template["declared_toolchain"]}
    return policy


def source_module(raw, path, name):
    # raw is the previously admitted byte snapshot; never reread/import by filename.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def admitted_sources(bindings):
    sources, pins = {}, {}
    for key in sorted(MODULE_KEYS):
        path = bindings["module_paths"][key]
        raw = regular(path, 128*1024)
        require(hashlib.sha256(raw).hexdigest() == bindings["module_hashes"][key],
                "wrapper source mismatch: " + key)
        sources[key], pins[path] = raw, bindings["module_hashes"][key]
    support = {}
    for key, (expected, size) in SUPPORT_PINS.items():
        path = bindings["final_helper"] if key == "final_helper" else bindings["support_arguments"][key]
        raw = regular(path, size)
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == expected,
                "immutable transitive helper/data mismatch: " + key)
        support[key], pins[path] = raw, expected
    return sources, support, pins


def support_graph(raw, bindings):
    paths = dict(bindings["support_arguments"], final_helper=bindings["final_helper"])
    h = source_module(raw["helper"], paths["helper"], "shipping_pr35_sources")
    q = source_module(raw["qualified_controller"], paths["qualified_controller"], "shipping_qualified_sources")
    c = source_module(raw["compact_controller"], paths["compact_controller"], "shipping_compact_sources")
    f = source_module(raw["final_helper"], paths["final_helper"], "shipping_final_sources")
    recipe, foundation, compact = (strict(raw[key]) for key in
                                  ("recipe", "qualified_manifest", "compact_manifest"))
    f.c, f.q, c.q = c, q, q
    # Do not invoke any legacy dynamic importer or DEV/TEST environment builder.
    f.support = lambda unused: (h, recipe, foundation, compact)
    return f, h, recipe, foundation, compact


HOST_SCOPE = "OBSERVED_SELECTED_HOST_IDENTITIES_NOT_A_TRANSITIVE_CLOSURE"
HOST_STDLIB = ["__future__","argparse","ast","base64","collections.abc","copy","ctypes","errno","gzip","hashlib","importlib.util","json","math","os","pathlib","queue","re","select","selectors","shutil","signal","socket","stat","statistics","struct","subprocess","sys","tarfile","tempfile","threading","time","types","typing","uuid"]
HOST_EXCLUSIONS = ["unimported stdlib files and later imports outside the fixed preload snapshot",
                   "Rust target rlibs and startup objects",
                   "unselected compiler/linker support and native transitive dependencies"]


def rust_library_name(name):
    return type(name) is str and "/" not in name and (
        name.startswith("librustc_driver-") and name.endswith(".so")
        or name.startswith("libLLVM") and (".so" in name))


def gcc_helper_paths(cc):
    name = Path(cc).name
    version = name.rsplit("-",1)[-1]
    if "gcc-" not in name or not version.isdigit():
        return []
    root = Path("/usr/lib/gcc/x86_64-linux-gnu")/version
    return [str(root/name) for name in ("cc1","collect2","liblto_plugin.so")]


def host_path_label(path, rust_lib):
    path = str(path)
    toolchain = str(Path(rust_lib).parent)
    if path.startswith(toolchain+"/"):
        return "rust-toolchain/"+path[len(toolchain)+1:]
    if path.startswith(("/usr/","/lib/","/etc/")):
        return path[:512]
    return "outside-declared-system-path"


def stdlib_origins():
    origins = {}
    for name,module in sorted(sys.modules.items()):
        if name.split(".",1)[0] not in sys.stdlib_module_names:
            continue
        spec = getattr(module,"__spec__",None)
        origin = getattr(spec,"origin",None)
        if origin in ("built-in","frozen",None):
            continue
        require(type(origin) is str and Path(origin).is_absolute()
                and origin.startswith("/usr/lib/python3.10/"), "unexpected loaded stdlib origin")
        cached = getattr(module,"__cached__",None)
        if cached is not None:
            require(type(cached) is str and cached.startswith("/usr/lib/python3.10/")
                    and Path(cached).is_absolute(), "unexpected stdlib cache origin")
        origins[name] = {"origin":origin,"cached":cached}
        require(len(origins) <= 256, "selected stdlib origin count")
    return origins


def selected_rust_libraries(root):
    root = Path(root)
    require(root.is_dir() and str(root.resolve()) == str(root), "canonical Rust library directory")
    selected, count = [], 0
    with os.scandir(root) as entries:
        for entry in entries:
            count += 1
            require(count <= 128, "shallow Rust library selection count")
            if rust_library_name(entry.name):
                selected.append(str(root/entry.name))
    require(0 < len(selected) <= 16 and any(Path(p).name.startswith("librustc_driver-")
            for p in selected), "bounded Rust compiler driver selection")
    return sorted(selected)


def progress_snapshot(progress):
    return {key:progress.get(key) for key in
            ("category","path_label","completed_files","current_file_bytes_read",
             "total_bytes_read","elapsed_seconds")}


def host_file(path, expected, deadline, progress=None):
    require(time.monotonic() < deadline, "host selected-identity deadline")
    path = Path(path)
    require(path.is_absolute() and str(path.resolve()) == str(path), "indirect host input")
    fd = open_regular_nofollow(path)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and type(expected["bytes"]) is int and
                before.st_size == expected["bytes"] and 0 <= before.st_size <= 512*1024**2 and
                hex_sha(expected["sha256"]), "host input shape/size")
        digest, count = hashlib.sha256(), 0
        while True:
            require(time.monotonic() < deadline, "host selected-identity deadline")
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            count += len(chunk)
            if progress is not None:
                progress["current_file_bytes_read"] = count
                progress["total_bytes_read"] += len(chunk)
                progress["elapsed_seconds"] = time.monotonic()-progress["started"]
            require(count <= expected["bytes"], "host input grew")
            digest.update(chunk)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns")
        require(count == expected["bytes"] and digest.hexdigest() == expected["sha256"] and
                all(getattr(before, key) == getattr(after, key) for key in fields), "host input changed")
    finally:
        os.close(fd)


def directory_identity(path):
    info = Path(path).stat()
    require(stat.S_ISDIR(info.st_mode) and str(Path(path).resolve()) == path,
            "canonical import directory identity")
    return {"device":info.st_dev,"inode":info.st_ino,"mode":info.st_mode,"uid":info.st_uid}


def host_lineage(host, bindings, deadline, progress=None):
    """Recheck exactly the first bounded selected observation, never rebaseline.
    Neither a Python filesystem census nor a complete compiler/native closure.
    """
    require(set(host) == {"schema","bootstrap","tools","files","search_paths","absent_paths",
            "versions","affinity","dependency_scope","links","stdlib_origins","python_imports",
            "rust_library_root","rust_libraries","selected_gcc_helpers","exclusions"}
            and host["schema"] == 2 and host["dependency_scope"] == HOST_SCOPE
            and host["exclusions"] == HOST_EXCLUSIONS
            and host["python_imports"] == HOST_STDLIB, "selected host schema/scope")
    require(sys.flags.isolated == 1 and sys.flags.no_site == 1 and
            sys.flags.dont_write_bytecode == 1 and sys.flags.optimize == 0, "isolated bootstrap")
    boot = host["bootstrap"]
    require(str(Path(sys.executable).resolve()) == boot["executable"] == bindings["python"]
            and sys.version == boot["version"] and list(sys.path) == boot["sys_path"],
            "bootstrap interpreter/import path differs")
    require([getattr(item,"__name__",type(item).__name__) for item in sys.meta_path] ==
            ["BuiltinImporter","FrozenImporter","PathFinder"], "custom import finder")
    require(0 < len(host["files"]) <= 512 and len(host["stdlib_origins"]) <= 256,
            "selected host file/module count")
    require(set(("cargo","rustc","git","cc","ld.lld","python")).issubset(host["tools"])
            and host["tools"]["python"] == bindings["python"], "declared host tools")
    for name,path in host["tools"].items():
        require(path in host["files"] and str(Path(path).resolve()) == path,
                "tool outside selected identities")
        if name != "python":
            require(str(Path(shutil.which(name,path=bindings["path"]) or "").resolve()) == path,
                    "declared tool resolution changed")
    for path,link in host["links"].items():
        require(os.path.islink(path) and os.readlink(path) == link["text"]
                and str(Path(path).resolve()) == link["target"] and link["target"] in host["files"],
                "selected host alias changed")
    for path,identity in host["search_paths"].items():
        require(time.monotonic() < deadline and directory_identity(path) == identity,
                "isolated search directory changed")
    for path in host["absent_paths"]:
        require(time.monotonic() < deadline and not os.path.lexists(path), "absent host path appeared")
    require(selected_rust_libraries(host["rust_library_root"]) == host["rust_libraries"]
            and gcc_helper_paths(host["tools"]["cc"]) == host["selected_gcc_helpers"],
            "selected compiler helper set changed")
    progress = progress if progress is not None else {
        "started":time.monotonic(),"total_bytes_read":0,"completed_files":0}
    try:
        for path,expected in host["files"].items():
            progress.update(category="selected-identity-recheck",
                path_label=host_path_label(path,host["rust_library_root"]),current_file_bytes_read=0)
            host_file(path,expected,deadline,progress)
            progress["completed_files"] += 1
        for name in HOST_STDLIB:
            require(time.monotonic() < deadline, "stdlib origin recheck deadline")
            importlib.import_module(name)
        current = stdlib_origins()
        require(all(current.get(name) == origin for name,origin in host["stdlib_origins"].items()),
                "preloaded stdlib origin changed")
        require(sorted(os.sched_getaffinity(0)) == host["affinity"], "CPU affinity differs")
    except BaseException as error:
        progress["elapsed_seconds"] = time.monotonic()-progress["started"]
        raise RuntimeError(str(error)+": "+json.dumps(progress_snapshot(progress),
                           sort_keys=True,separators=(",",":"))) from error
    return {"status":"SELECTED_HOST_IDENTITIES_UNCHANGED","files":len(host["files"]),
            "bytes_rechecked":progress["total_bytes_read"],"affinity":host["affinity"],
            "dependency_scope":HOST_SCOPE,"exclusions":HOST_EXCLUSIONS,
            "elapsed_seconds":time.monotonic()-progress["started"]}


def prepare_and_describe(f, h, recipe, foundation, compact, args, build, sup, root, evidence, env, host):
    # Every legacy validation and Runner operation is inside the outer hard supervisor.
    require(recipe["production_stage_trees"]["final"] == "7dec0c811a514adf32a70907635939547e0a57cf",
            "PR35 recipe identity")
    f.q.validate_manifest(h, foundation)
    f.c.validate(h, compact, foundation)
    prepared = build.prepare(f, args, root, evidence / "source-commands", env)
    versions = {}
    for label, argv in (("rustc", ["rustc", "-Vv"]), ("cargo", ["cargo", "-V"]),
                        ("cc", ["cc", "--version"]), ("lld", ["ld.lld", "--version"])):
        directory = evidence / ("version-" + label)
        sup.command(argv, str(root), env, directory, 10, 65536)
        versions[label] = (directory / "stdout.raw").read_text()
    require((not host["versions"] or versions == host["versions"])
            and versions["cargo"].startswith("cargo 1.95.0 ")
            and "release: 1.95.0\n" in versions["rustc"]
            and "host: x86_64-unknown-linux-gnu\n" in versions["rustc"], "toolchain/host mismatch")
    prepared["host"] = {"versions": versions, "uname": list(os.uname()),
                        "affinity": sorted(os.sched_getaffinity(0)),
                        "clock_ticks": os.sysconf("SC_CLK_TCK"), "environment": env}
    return prepared


def postflight(f, h, build, prepared, env, pins, executables, host, bindings, root, evidence, deadline):
    runner = h.Runner(evidence / "postflight", root, max(1, deadline-time.monotonic()))
    receipts = {}
    for arm in ("baseline", "candidate", "modules"):
        source = Path(prepared["modules"] if arm == "modules" else prepared["sources"][arm])
        expected = prepared["foundation"]["fixture"]["tree"] if arm == "modules" else TREES[arm]
        receipts[arm] = f.q.postflight(h, runner, arm, source, env, prepared["snapshots"][arm], expected)
        build.clean_source_paths(source, prepared["snapshots"][arm])
        build.cargo_configuration(source, env, prepared["snapshots"][arm])
    for path, expected in pins.items():
        require(build.file_hash(path) == expected, "runtime/import/config input changed")
    for receipt in executables:
        current = build.executable_receipt(receipt["path"])
        require(current == {key: receipt[key] for key in current}, "shipping executable postflight changed")
    host_receipt = host_lineage(host, bindings, deadline)
    require(time.monotonic() < deadline, "postflight deadline")
    return {"status": "SOURCE_EXECUTABLE_IMPORT_POSTFLIGHT_COMPLETE", "sources": receipts,
            "host": host_receipt, "stages": runner.records}



def guarded_build(operation, arguments, host, bindings, deadline):
    # Revalidate executable/compiler/import dependencies immediately before each
    # build inside that build's existing hard 1800 s envelope.
    host_lineage(host, bindings, deadline-5)
    return operation(*arguments)


def runtime_preflight(build, pins, host, bindings, deadline):
    host_receipt = host_lineage(host, bindings, deadline-5)
    for path, expected in pins.items():
        require(time.monotonic() < deadline-5 and build.file_hash(path) == expected,
                "runtime/import input mismatch")
    return {"status": "RUNTIME_INPUTS_ADMITTED", "host": host_receipt, "pins": pins}


def control_remaining(budget, now):
    """All wall time is control time except bounded supervised build/cell calls."""
    require(type(now) in (int, float) and math.isfinite(now), "control clock")
    started = budget["started"]
    excluded = budget["excluded_noncontrol_seconds"]
    require(type(started) in (int, float) and math.isfinite(started)
            and type(excluded) in (int, float) and math.isfinite(excluded)
            and 0 <= excluded <= now-started, "control accounting")
    remaining = 300.0 - (now-started-excluded)
    require(math.isfinite(remaining), "nonfinite control budget")
    budget["remaining_seconds"] = remaining
    return remaining


def stage(sup, capture, operation, arguments, shared, seconds, result, deadline, status,
          noncontrol_budget=None, noncontrol_phase=None):
    remaining = min(seconds, deadline-time.monotonic())
    require(remaining > 5, "attempt deadline")
    if noncontrol_budget is not None:
        require(control_remaining(noncontrol_budget, time.monotonic()) > 0,
                "control allowance exhausted before non-control stage")
    observer = None if noncontrol_budget is None else noncontrol_budget.get("outer_observer")
    if observer is not None:
        require(noncontrol_phase in ("build-baseline","build-candidate","build-reference"),
                "declared build clock phase")
        observer({"event":"begin", "phase":noncontrol_phase, "cap_seconds":remaining,
                  "at":time.monotonic()})
    stage_started = time.monotonic()
    try:
        guard = sup.supervise(capture, operation, arguments, shared, {"other": 48}, remaining,
                              result, result_pipe_cap=4*sup.MIB+65536)
    finally:
        if noncontrol_budget is not None:
            # Never exclude over-deadline time or parent work outside this call.
            call_finished = time.monotonic()
            excluded = min(remaining, max(0.0, call_finished-stage_started))
            noncontrol_budget["excluded_noncontrol_seconds"] += excluded
            control_remaining(noncontrol_budget, time.monotonic())
            if observer is not None:
                observer({"event":"end", "phase":noncontrol_phase, "call_started":stage_started,
                          "call_finished":call_finished, "excluded_seconds":excluded,
                          "cumulative_excluded_seconds":noncontrol_budget["excluded_noncontrol_seconds"]})
    # The hard worker persists and hashes the complete result before sending its
    # bounded control value. Never read a potentially torn result in the parent.
    status["stages"].append({key: value for key, value in guard.items() if key != "value"})
    require(guard["status"] == "SUPERVISED_STAGE_COMPLETE", "supervised stage failed")
    require(isinstance(guard.get("result_receipt"), dict), "missing durable result receipt")
    return guard["value"]

def observe_host(policy, bindings, deadline, progress):
    """Bounded relevant host identities; no recursive host filesystem traversal."""
    require(set(policy) == {"schema","python","python_import_roots","absent_import_paths",
            "tools","support_files","rust_library_root","python_imports","execution_context",
            "declared_toolchain"} and policy["schema"] == 2
            and policy["python_imports"] == HOST_STDLIB, "selected host policy")
    require(policy["declared_toolchain"] == {"rust":"1.95.0","target":"x86_64-unknown-linux-gnu"}
            and policy["python"] == bindings["python"], "declared host invariants")
    require(policy["execution_context"] and all(os.environ.get(key) == value
            for key,value in policy["execution_context"].items()), "execution origin differs")
    require(len(policy["tools"]) <= 32 and len(policy["support_files"]) <= 128
            and len(policy["python_import_roots"]) <= 8, "selected host policy budget")
    require(set(sys.path) == set(policy["python_import_roots"]) | set(policy["absent_import_paths"])
            and len(sys.path) == len(set(sys.path)), "unreviewed Python search path")
    require([getattr(item,"__name__",type(item).__name__) for item in sys.meta_path] ==
            ["BuiltinImporter","FrozenImporter","PathFinder"], "custom import finder")
    files,links = {},{}
    absent = set(policy["absent_import_paths"])
    def add_file(path, category):
        require(time.monotonic() < deadline and len(files) < 512, "selected observation deadline/count")
        path = str(Path(path).resolve())
        if path in files:
            return
        progress.update(category=category,path_label=host_path_label(path,policy["rust_library_root"]),
                        current_file_bytes_read=0,elapsed_seconds=time.monotonic()-progress["started"])
        fd = open_regular_nofollow(path)
        try:
            before = os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= 512*1024**2,
                    "selected observation file type/size")
            digest,count = hashlib.sha256(),0
            while True:
                require(time.monotonic() < deadline, "host observation deadline")
                piece = os.read(fd,65536)
                if not piece:
                    break
                count += len(piece)
                progress["current_file_bytes_read"] = count
                progress["total_bytes_read"] += len(piece)
                progress["elapsed_seconds"] = time.monotonic()-progress["started"]
                require(count <= before.st_size and progress["total_bytes_read"] <= 4*1024**3,
                        "unchanged host observation byte budget")
                digest.update(piece)
            after = os.fstat(fd)
            fields=("st_dev","st_ino","st_mode","st_uid","st_gid","st_size","st_mtime_ns","st_ctime_ns")
            require(count == before.st_size and all(getattr(before,k) == getattr(after,k)
                    for k in fields), "selected host file changed during read")
            files[path]={"bytes":count,"sha256":digest.hexdigest()}
            progress["completed_files"] = len(files)
        finally:
            os.close(fd)
    def add_input(path, category):
        if Path(path).is_symlink():
            links[str(path)]={"text":os.readlink(path),"target":str(Path(path).resolve())}
        add_file(path,category)
    progress.update(category="fixed-stdlib-preload",path_label=None)
    for name in HOST_STDLIB:
        require(time.monotonic() < deadline,"fixed stdlib preload deadline")
        progress["path_label"] = name
        importlib.import_module(name)
    origins = stdlib_origins()
    search_paths = {path:directory_identity(path) for path in policy["python_import_roots"]}
    tools = {name:str(Path(path).resolve()) for name,path in policy["tools"].items()}
    for name,path in policy["tools"].items():
        add_input(path,"tool:"+name)
    for origin in origins.values():
        add_input(origin["origin"],"loaded-stdlib")
        cached = origin["cached"]
        if cached is not None:
            if os.path.lexists(cached):
                add_input(cached,"loaded-stdlib-cache")
            else:
                absent.add(cached)
    rust_libraries = selected_rust_libraries(policy["rust_library_root"])
    for path in rust_libraries:
        add_input(path,"selected-rust-compiler-library")
    gcc_helpers = gcc_helper_paths(tools["cc"])
    for path in gcc_helpers:
        add_input(path,"selected-gcc-helper")
    for path in policy["support_files"]:
        add_input(path,"declared-system-support")
    progress.update(category="loaded-native-map",path_label="/proc/self/maps")
    with open("/proc/self/maps","r",encoding="utf-8") as stream:
        maps=stream.read(1024*1024+1)
    require(len(maps.encode()) <= 1024*1024, "bootstrap map byte cap")
    for line in maps.splitlines():
        fields=line.split(None,5)
        if len(fields)==6 and fields[5].startswith("/"):
            require(not fields[5].endswith(" (deleted)"),"deleted loaded native input")
            add_input(fields[5],"loaded-native-map")
    require(time.monotonic() < deadline,"selected observation final deadline")
    observed={"schema":2,"bootstrap":{"executable":str(Path(sys.executable).resolve()),
        "version":sys.version,"sys_path":list(sys.path)},"tools":tools,"files":files,
        "search_paths":search_paths,"absent_paths":sorted(absent),"links":links,
        "versions":{},"affinity":sorted(os.sched_getaffinity(0)),"dependency_scope":HOST_SCOPE,
        "stdlib_origins":origins,"python_imports":HOST_STDLIB,
        "rust_library_root":policy["rust_library_root"],"rust_libraries":rust_libraries,
        "selected_gcc_helpers":gcc_helpers,"exclusions":HOST_EXCLUSIONS}
    progress["elapsed_seconds"]=time.monotonic()-progress["started"]
    # No immediate second whole-inventory read. Each selected file was hashed
    # once with stable descriptor metadata; later stages recheck this same set.
    return {"host":observed,"verification":{"status":"FIRST_SELECTED_HOST_OBSERVATION_COMPLETE",
            "files":len(files),"progress":progress_snapshot(progress),"dependency_scope":HOST_SCOPE},
            "execution_context":{key:os.environ.get(key) for key in sorted(set(policy["execution_context"]) |
                {"GITHUB_RUN_ID","GITHUB_RUN_ATTEMPT","ImageVersion"})},
            "native_dependency_claim":"SELECTED_OBSERVED_IDENTITIES_NOT_COMPLETE_TOOLCHAIN_OR_NATIVE_CLOSURE"}


def bootstrap_host(policy, bindings, deadline, observed_host=None):
    """Trusted stdlib-only hard admission watchdog; no product or helper imports."""
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        progress={"started":time.monotonic(),"category":"bootstrap","path_label":None,
                  "completed_files":0,"current_file_bytes_read":0,"total_bytes_read":0,"elapsed_seconds":0.0}
        try:
            os.setsid()
            value = (observe_host(policy, bindings, deadline-5, progress) if observed_host is None else
                     {"verification":host_lineage(observed_host,bindings,deadline-5,progress)})
            raw = json.dumps({"status": "ADMITTED", "value": value}, separators=(",", ":")).encode()
            require(len(raw) <= 4*1024**2, "host admission receipt size")
            written = 0
            while written < len(raw):
                require(time.monotonic() < deadline-5, "host receipt pipe deadline")
                written += os.write(writer, raw[written:])
            os._exit(0)
        except BaseException as error:
            progress["elapsed_seconds"]=time.monotonic()-progress["started"]
            os.write(writer, json.dumps({"status": "FAILED_CENSORED",
                "error": type(error).__name__ + ": " + str(error)[:2048],
                "observation_progress":progress_snapshot(progress)}).encode())
            os._exit(1)
    os.close(writer)
    os.set_blocking(reader, False)
    fd, observed, data = None, None, bytearray()
    try:
        fd = os.pidfd_open(pid)
        while observed is None:
            try:
                piece = os.read(reader, 65536)
                data.extend(piece)
                require(len(data) <= 4*1024**2, "host admission output cap")
            except BlockingIOError:
                pass
            got, state = os.waitpid(pid, os.WNOHANG)
            if got:
                observed = state
                break
            require(time.monotonic() < deadline-5, "host admission hard deadline")
            time.sleep(0.05)
        while True:
            try:
                piece = os.read(reader, 65536)
            except BlockingIOError:
                break
            if not piece:
                break
            data.extend(piece)
            require(len(data) <= 4*1024**2, "host admission output cap")
        result = strict(bytes(data))
        require(observed == 0 and result["status"] == "ADMITTED", "host admission rejected: " + str(result))
        return result["value"]
    finally:
        if observed is None:
            try:
                if fd is not None:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                else:
                    # This direct child has not been reaped, so its PID cannot
                    # have been reused if pidfd acquisition itself failed.
                    os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            while time.monotonic() < deadline:
                got, _ = os.waitpid(pid, os.WNOHANG)
                if got:
                    observed = -1
                    break
                time.sleep(0.02)
            require(observed is not None, "host admission cleanup uncertainty")
        if fd is not None:
            os.close(fd)
        os.close(reader)


def admit_entry_inputs(authorization_path, bindings_path, mode, outer_observer, outer_started):
    # No imported drafted source, command, work directory or source mutation before this seal.
    require(AUTHORIZATION_SHA256 is not None, "HOLD: root execution approval is not sealed")
    entered = time.monotonic()
    require(type(outer_started) in (int,float) and math.isfinite(outer_started)
            and 0 <= entered-outer_started <= 60, "original outer attempt origin")
    started = outer_started
    global_deadline = started+(300 if mode == "host-admission-only" else 12000)
    control_budget = {"started": started, "excluded_noncontrol_seconds": 0.0,
                      "remaining_seconds": 300.0, "outer_observer": outer_observer}
    require(hex_sha(AUTHORIZATION_SHA256) and hash_file(authorization_path) == AUTHORIZATION_SHA256,
            "authorization differs")
    authorization = strict(regular(authorization_path, 4*1024**2))
    expected_status = {"four-resource-smoke":"ROOT_APPROVED_FOUR_RESOURCE_FEASIBILITY_SMOKE",
                       "host-admission-only":"ROOT_APPROVED_HOST_ADMISSION_ONLY"}
    require(mode in expected_status and authorization["mode"] == mode
            and authorization["status"] == expected_status[mode]
            and authorization["plan_sha256"] == PLAN_SHA
            and authorization["bindings_sha256"] == hash_file(bindings_path), "scope/bindings differ")
    require((mode == "four-resource-smoke" and callable(outer_observer)
             and authorization["outer_clock_protocol"] == "FIXED_SEVEN_PHASE_ACK_V1")
            or (mode == "host-admission-only" and outer_observer is None
                and authorization["outer_clock_protocol"] == "HOST_ONLY_NO_PHASES_V1"),
            "mode-specific outer clock admission")
    binding_template = strict(regular(bindings_path, 4*1024**2))
    bindings, resolution = resolve_binding_template(binding_template, str(Path(__file__).resolve()))
    admit_maps(bindings, authorization)
    # The template digest avoids the authorization/entry self-hash cycle. The
    # sole reviewed seal line may change from None to this exact authorization hash.
    entry_raw = regular(str(Path(__file__).resolve()), 128*1024)
    lines = entry_raw.splitlines(keepends=True)
    seal_lines = [i for i, line in enumerate(lines) if line.startswith(b"AUTHORIZATION_SHA256 = ")]
    require(len(seal_lines) == 1, "entry seal line ambiguity")
    lines[seal_lines[0]] = b"AUTHORIZATION_SHA256 = None\n"
    require(hashlib.sha256(b"".join(lines)).hexdigest() == authorization["reviewed_entry_template_sha256"],
            "entry template differs")
    require(hash_file(bindings["final_pass_receipt"]) == FINAL_PASS and
            bindings["source_trees"] == TREES, "qualified source identities differ")
    require(hash_file(bindings["baseline_qualification_receipt"]) == BASELINE_PASS,
            "baseline must be exact qualified PRODUCTION tree, not historical baseline controls")
    baseline_proof = strict(regular(bindings["baseline_qualification_receipt"], 256*1024))
    require(baseline_proof["disposition"] == "EXACT_CURRENT_GRAPH_HOSTED_QUALIFICATION_PASS"
            and baseline_proof["source_trees"]["production"] == TREES["baseline"]
            and baseline_proof["production"]["status"] == "CURRENT_GRAPH_PRODUCTION_EXACT_PASS"
            and baseline_proof["run"]["head"] == "ad1f0a1c201b57602a6f572bc134061660e8ef31",
            "wrong baseline qualification meaning")
    raw, support, pins = admitted_sources(bindings)
    model_raw = regular(bindings["model_fixture"], 128*1024)
    require(hashlib.sha256(model_raw).hexdigest() == authorization["model_fixture_sha256"],
            "model fixture differs")
    pins[bindings["model_fixture"]] = authorization["model_fixture_sha256"]
    host_raw = regular(bindings["host_policy"], 128*1024)
    require(hashlib.sha256(host_raw).hexdigest() == authorization["host_policy_sha256"],
            "declared host policy differs")
    host_template = strict(host_raw)
    host_policy = resolve_host_template(host_template, bindings, resolution)
    # Bootstrap, imports, parent filesystem work and all early reads are charged.
    bootstrap_seconds = min(60, control_remaining(control_budget, time.monotonic())-180)
    require(bootstrap_seconds > 5, "bootstrap control reserve")
    host_receipt = bootstrap_host(host_policy, bindings,
                                  min(global_deadline, time.monotonic()+bootstrap_seconds))
    host = host_receipt.pop("host")
    control_remaining(control_budget, time.monotonic())
    # All authored source maps/helpers/manifests and selected host identities
    # are admitted before the first exec of downloaded top-level Python.
    return (started, entered, global_deadline, control_budget, authorization, bindings,
            raw, support, pins, host_receipt, host, entry_raw, host_policy, resolution)


def host_admission_only(authorization_path, bindings_path, outer_started):
    """Exact shared admission only; never source preparation, build, or cell code."""
    require(AUTHORIZATION_SHA256 is not None, "HOLD: root execution approval is not sealed")
    (started, entered, global_deadline, controls, authorization, bindings,
     raw, support, pins, receipt, host, entry_raw, host_policy, resolution) = admit_entry_inputs(
        authorization_path, bindings_path, "host-admission-only", None, outer_started)
    recheck_seconds = min(30,control_remaining(controls,time.monotonic())-30)
    require(recheck_seconds > 5, "host-only original control reserve")
    recheck = bootstrap_host(host_policy,bindings,
        min(global_deadline,time.monotonic()+recheck_seconds),observed_host=host)
    remaining = control_remaining(controls,time.monotonic())
    require(remaining > 30 and controls["excluded_noncontrol_seconds"] == 0,
            "host-only control allowance")
    return {"status":"HOST_ADMISSION_COMPLETE","mode":"host-admission-only",
            "host_observation":receipt,"selected_host":host,"host_recheck":recheck,
            "resolution":resolution,"host_policy_sha256":authorization["host_policy_sha256"],
            "attempt_started_monotonic":started,"entry_started_monotonic":entered,
            "excluded_noncontrol_seconds":0.0,"controls_seconds_remaining":remaining,
            "elapsed_seconds":time.monotonic()-started,"performance_claim":None,
            "not_run":["source_preparation","shipping_builds","resource_procedures","replay"],
            "qualification":"HOST_IDENTITIES_ONLY_NOT_RESOURCE_FEASIBILITY"}


def entry(authorization_path, bindings_path, work_path, evidence_path, outer_observer=None, outer_started=None):
    require(AUTHORIZATION_SHA256 is not None, "HOLD: root execution approval is not sealed")
    (started, entered, global_deadline, control_budget, authorization, bindings,
     raw, support, pins, host_receipt, host, entry_raw, host_policy, resolution) = admit_entry_inputs(
        authorization_path, bindings_path, "four-resource-smoke", outer_observer, outer_started)
    modules = {key: source_module(raw[key], bindings["module_paths"][key], "shipping_smoke_" + key)
               for key in sorted(MODULE_KEYS)}
    f, h, recipe, foundation, compact = support_graph(support, bindings)
    p, sup, capture, build, dispatch = (modules[key] for key in
                                      ("primitives", "supervisor", "capture", "build", "dispatch"))
    work, evidence = Path(work_path), Path(evidence_path)
    require(work.is_absolute() and evidence.is_absolute() and str(work.resolve()) == str(work)
            and str(evidence.resolve()) == str(evidence) and not os.path.lexists(work) and not os.path.lexists(evidence)
            and work.parent.is_dir() and evidence.parent.is_dir()
            and not evidence.is_relative_to(work) and not work.is_relative_to(evidence),
            "fresh canonical disjoint owned roots required")
    require(shutil.disk_usage(work.parent).free >= 8*1024**3
            and shutil.disk_usage(evidence.parent).free >= 8*1024**3, "initial disk below 8 GiB")
    work.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    shared, source_root = work / "shared", work / "source"
    home, cargo = work / "home", work / "cargo"
    for directory in (shared, source_root, home, cargo):
        directory.mkdir(mode=0o700)
    ledger = sup.new_ledger()
    env = p.release_environment(home, cargo, bindings["rustup_home"], bindings["path"])
    build.require_release_environment(env)
    args = types.SimpleNamespace(**bindings["support_arguments"])
    args.publication = bindings["publication"]
    pins.update({authorization_path: AUTHORIZATION_SHA256, bindings_path: authorization["bindings_sha256"],
                 bindings["final_pass_receipt"]: FINAL_PASS,
                 bindings["baseline_qualification_receipt"]: BASELINE_PASS,
                 bindings["host_policy"]: authorization["host_policy_sha256"],
                 str(Path(__file__).resolve()): hashlib.sha256(entry_raw).hexdigest()})
    status = {"status": "FAILED_CENSORED", "plan_sha256": PLAN_SHA, "stages": [],
              "authorization_sha256": AUTHORIZATION_SHA256, "source_trees": TREES,
              "baseline_qualification_sha256": BASELINE_PASS, "final_qualification_sha256": FINAL_PASS,
              "host_admission": host_receipt, "performance_claim": None,
              "replay_fixture_nonstart": "NOT_INDEPENDENTLY_OBSERVED",
              "replay_substitution": "SOURCE_VERIFIED_REPLAY_SUBSTITUTION"}
    prepared, binaries, reference = None, {}, None
    try:
        sup.write_json(shared / "admission.json", {"pins": pins, "module_hashes": bindings["module_hashes"],
                       "environment": env, "bootstrap": host["bootstrap"], "tools": host["tools"],
                       "declared_host_policy_sha256": authorization["host_policy_sha256"]})
        sup.write_json(shared/"host-observed.json", host)
        sup.write_json(shared/"resolved-admission.json", {"resolution":resolution,
            "binding_template_sha256":authorization["bindings_sha256"],
            "host_template_sha256":authorization["host_policy_sha256"],
            "resolved_bindings":bindings, "resolved_host_policy":host_policy,
            "scope":"OBSERVED_RESOLUTION_NOT_PREDECLARED_HOST_HASHES"})
        control_started = time.monotonic()
        try:
            prepared = stage(sup, capture, prepare_and_describe,
                (f, h, recipe, foundation, compact, args, build, sup, source_root, shared, env, host),
                shared, min(180, control_remaining(control_budget, time.monotonic())-180), shared/"prepared.json", global_deadline, status)
        finally:
            control_remaining(control_budget, time.monotonic())
        host["versions"] = prepared["host"]["versions"]
        sup.write_json(shared/"host-with-versions.json", host)
        for arm in ("baseline", "candidate"):
            require(shutil.disk_usage(work).free >= 8*1024**3, "build admission below 8 GiB")
            binaries[arm] = stage(sup, capture, guarded_build,
                (build.build_core, (p, sup, arm, prepared, work/("target-"+arm), env, shared/(arm+"-build")),
                 host, bindings, min(global_deadline, time.monotonic()+1800)),
                shared, 1800, shared/(arm+"-build.json"), global_deadline, status,
                noncontrol_budget=control_budget, noncontrol_phase="build-"+arm)
        require(shutil.disk_usage(work).free >= 8*1024**3, "reference build admission below 8 GiB")
        reference = stage(sup, capture, guarded_build,
            (build.build_reference,
             (f, h, p, sup, prepared, work/"target-reference", env, bindings["python"], shared/"reference-build"),
             host, bindings, min(global_deadline, time.monotonic()+1800)),
            shared, 1800, shared/"reference-build.json", global_deadline, status,
            noncontrol_budget=control_budget, noncontrol_phase="build-reference")
        baseline = Path(prepared["sources"]["baseline"])
        paths = {"reference": reference["path"], "python": bindings["python"],
                 "model_fixture": bindings["model_fixture"],
                 "probe_fixture": str(baseline/"crates/proteus-core/tests/fixtures/process_probe_tool.py"),
                 "runtime_dir": str(baseline/"examples/modules")}
        pins.update({paths["probe_fixture"]: "d145d80c03639c2486b62d772c2a0013b3597c7ea4905eb90d5d439a05498df4",
            str(Path(paths["runtime_dir"])/"component_runtime.py"):
                "1605424f24d92086357e1a046cd9db41075eeb0fb80ffdb707d07165af162048",
            paths["python"]: host["files"][paths["python"]]["sha256"],
            paths["reference"]: reference["sha256"],
            **{value["path"]: value["sha256"] for value in binaries.values()}})
        control_started = time.monotonic()
        try:
            deadline = min(global_deadline, time.monotonic()+min(30, control_remaining(control_budget, time.monotonic())-180))
            status["runtime_admission"] = stage(sup, capture, runtime_preflight,
                (build, pins, host, bindings, deadline), shared, deadline-time.monotonic(),
                shared/"runtime-admission.json", global_deadline, status)
        finally:
            control_remaining(control_budget, time.monotonic())
        workspace = work/"workspace"
        workspace.mkdir(mode=0o700)
        runtime = {"attempt_id": authorization["attempt_id"], "binaries": binaries, "paths": paths,
                   "runtime_env": env, "workspace": str(workspace), "evidence_ledger": ledger,
                   "global_deadline": global_deadline, "attempt_deadline": global_deadline,
                   "control_budget": control_budget, "control_sync": control_remaining,
                   "input_files": [{"path": path, "sha256": value} for path, value in sorted(pins.items())],
                   "replay_source_leaves": prepared["replay_source_leaves"]}
        require(time.monotonic() < global_deadline-90, "no remaining cleanup/control reserve")
        result = dispatch.four(modules, runtime, work, evidence/"procedures", AUTHORIZATION_SHA256)
        status["smoke"] = result
        require(result["status"] == "FEASIBILITY_SMOKE_COMPLETE", "four-procedure feasibility failed")
        status["status"] = "PENDING_SOURCE_EXECUTABLE_POSTFLIGHT"
    except BaseException as error:
        status["error"] = type(error).__name__ + ": " + str(error)[:2048]
        status["status"] = "FAILED_CENSORED"
    finally:
        # Source/executable/import postflight is attempted on failures too and
        # remains independently hard-supervised. It can never restore failed smoke.
        if prepared is not None:
            control_started = time.monotonic()
            try:
                deadline = min(global_deadline, time.monotonic()+min(60, control_remaining(control_budget, time.monotonic())-120))
                executables = list(binaries.values()) + ([reference] if reference else [])
                result = stage(sup, capture, postflight,
                    (f, h, build, prepared, env, pins, executables, host, bindings, work, shared, deadline-5),
                    shared, deadline-time.monotonic(), shared/"postflight.json", global_deadline, status)
                status["postflight"] = result
                if status["status"] == "PENDING_SOURCE_EXECUTABLE_POSTFLIGHT":
                    status["status"] = "FEASIBILITY_SMOKE_COMPLETE"
            except BaseException as error:
                status["status"] = "FAILED_CENSORED"
                status["postflight_error"] = type(error).__name__ + ": " + str(error)[:2048]
            finally:
                control_remaining(control_budget, time.monotonic())
        status["elapsed_seconds"] = time.monotonic()-started
        status["controls_seconds_remaining"] = control_remaining(control_budget, time.monotonic())
        # Finalizer owns shared retention, final.json and the bounded compressed
        # package. No direct parent copying/manifest write can bypass its ledger.
        final_started = time.monotonic()
        final_deadline = min(global_deadline, final_started+min(120, control_remaining(control_budget, time.monotonic())-30))
        try:
            final = sup.finalize(capture, shared, evidence, status, ledger, final_deadline)
        except BaseException as error:
            final = dict(status, status="FAILED_CENSORED",
                         finalization_error=type(error).__name__ + ": " + str(error)[:2048],
                         artifact_acceptance="NOT_ACCEPTED")
        finally:
            control_remaining(control_budget, time.monotonic())
        # This bounded terminal value belongs to the outer launcher's separately
        # reserved sidecar, not the already completed inner package manifest.
        final["controls_seconds_remaining"] = control_remaining(control_budget, time.monotonic())
        if final["controls_seconds_remaining"] <= 0:
            final["status"] = "FAILED_CENSORED"
            final["artifact_acceptance"] = "NOT_ACCEPTED"
            final["control_budget_error"] = "all-wall control allowance exhausted"
        final["elapsed_seconds"] = time.monotonic()-started
        final["entry_started_monotonic"] = entered
        final["attempt_started_monotonic"] = started
        final["excluded_noncontrol_seconds"] = control_budget["excluded_noncontrol_seconds"]
        return final
