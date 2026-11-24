#!/usr/bin/env python3
"""Offline native proof for reusing the owned session journal description path."""
import argparse
import json
from itertools import permutations
from pathlib import Path
import shutil
import subprocess
from native_inputs import HERE, TOOL_PINS, cargo, git_blob, need, sha, stage_native_inputs

SRC = Path("storage/session-storage/src")
COMPONENTS = {
    "fallback": ("source.patch", "f9dc989131cd560d4b40fb6a78d891699d978688", {
        SRC/"service/sessions.rs": ("38bf128b21df0592ad64e11d4c6815c87a272d98", "87905b496ace48438d0f75d3cade488560fc2b9f")}),
    "582": ("composition-582.patch", "fadf4a5955552382c8def044f18d54482181a0b1", {
        SRC/"service/views.rs": ("cd578af057e066e4e1620d2f014ebc52fdaa934c", "4e91d5fd6badfc7377a6d5ad3fff6b14127cb0fa"),
        SRC/"snapshot.rs": ("ecf417d4ebc712d2c5f724ced3fb676363f39fa6", "6f42ed3b0ac96b47df314f5e42736e4433480a6d")}),
}

def git_apply(w, arm, name, reverse=False):
    file, pin, scope = COMPONENTS[name]
    p = HERE/file
    need(git_blob(p.read_bytes()) == pin, "pinned exact patch")
    cmd = ["git", "apply", "--whitespace=error-all"] + (["--reverse"] if reverse else [])
    env = {"PATH":"/usr/bin:/bin", "HOME":str(w/"cargo-home"), "LC_ALL":"C.UTF-8",
           "GIT_CONFIG_GLOBAL":"/dev/null", "GIT_CONFIG_NOSYSTEM":"1", "GIT_CEILING_DIRECTORIES":str(w)}
    def git(*args):
        return subprocess.check_output([*cmd, *args, p], cwd=arm, env=env, text=True, timeout=30)
    matrix = [line.split("\t") for line in git("--numstat").splitlines()]
    need({Path(row[2]) for row in matrix} == set(scope), f"exact {name} scope")
    if name == "fallback":
        need([row[:2] for row in matrix] == [["1","1"]], "one-line product replacement")
    for path, (a, b) in scope.items():
        need(git_blob((arm/path).read_bytes()) == (b if reverse else a), "patch preimage")
    git("--check")
    git()
    for path, (a, b) in scope.items():
        need(git_blob((arm/path).read_bytes()) == (a if reverse else b)
             and (arm/path).stat().st_mode & 0o777 == 0o644, "patch postimage and mode")

def compose(w, stock):
    paths = sorted({path for _, _, scope in COMPONENTS.values() for path in scope})
    seen = {}
    for i, order in enumerate(permutations(COMPONENTS)):
        d = w/f"composition-{i}"
        for path in paths:
            (d/path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stock/path, d/path)
        active = set()
        def record():
            need({f.relative_to(d) for f in d.rglob("*") if f.is_file()} == set(paths), "composed exact scope")
            hashes = {p.as_posix():git_blob((d/p).read_bytes()) for p in paths}
            label = "+".join(sorted(active)) or "stock"
            need(seen.setdefault(label, hashes) == hashes, "both apply/reverse orders preserve exact bytes")
        record()
        for n in order:
            git_apply(w, d, n)
            active.add(n)
            record()
        for n in reversed(order):
            git_apply(w, d, n, True)
            active.remove(n)
            record()
    need(len(seen) == 4, "all patch subsets")
    return seen

def attach(arm):
    dst = arm/SRC/"tests/r276_fallback"
    dst.mkdir()
    for a, b in [("native.rs","mod.rs"), ("meter.rs","meter.rs")]:
        shutil.copyfile(HERE/a, dst/b)
    with (dst.parent/"mod.rs").open("a") as f:
        f.write("\nmod r276_fallback;\n")

def build(w, t, arm, profile, feature):
    p = ["--release"] if profile == "release" else []
    f = [] if feature == "default" else ["--features", "serde_json/preserve_order"]
    cargo(w, t, arm, "clean", "-p", "session-storage", *p, capture=True)
    out = cargo(w, t, arm, "test", "-p", "session-storage", "--no-run", "--message-format=json", *p, *f, capture=True)
    def is_test(e):
        return (e.get("reason") == "compiler-artifact" and e["target"]["name"] == "session_storage"
                and e["profile"]["test"] and e.get("executable"))
    [e] = [event for line in out.splitlines() if line.startswith("{") and is_test(event := json.loads(line))]
    manifest = w/"native"/arm/"storage/session-storage/Cargo.toml"
    need(not e["fresh"] and Path(e["manifest_path"]) == manifest
         and Path(e["target"]["src_path"]) == manifest.parent/"src/lib.rs", "fresh exact native leaf")
    b = w/f"{arm}-{profile}-{feature}"
    shutil.copyfile(e["executable"], b)
    b.chmod(0o755)
    return b

def execute(w, exe, name, mode=None, pair=None):
    env = {"PATH":"/usr/bin:/bin", "HOME":str(w/"cargo-home"), "TMPDIR":str(w/"tmp"), "LC_ALL":"C.UTF-8"}
    args = [exe, "--nocapture", "--test-threads=1"]
    if mode:
        env.update(R276F_MODE=mode, R276F_PAIR=str(pair))
        args.append("r276_fallback_pair")
    out = subprocess.run(args, cwd=w, env=env, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=150)
    (w/f"{name}.log").write_text(out.stdout)
    print(out.stdout if out.returncode else "\n".join(x for x in out.stdout.splitlines()
          if "R276F " in x or "test result:" in x), flush=True)
    need(out.returncode == 0, "native executable")
    return out.stdout

def parse_events(out):
    return {value["case"]:value for line in out.splitlines() if "R276F " in line
            for value in [json.loads(line.split("R276F ",1)[1])]}

def execute_pair(w, bins, profile, feature, repeat):
    prefix = f"{profile}-{feature}-pair-{repeat}"
    pair = w/prefix
    pair.mkdir()
    execute(w, bins["stock"], f"{prefix}-seed", "seed", pair)
    arms = {arm: parse_events(execute(w, bins[arm], f"{prefix}-{arm}", arm, pair)) for arm in bins}
    a, b = (arms["stock"], arms["candidate"])
    need(set(a) == set(b) == {f"{p}-{s}" for p in ("jsonl","sqlite") for s in
               ("directory","journal","one","many","absent","zero")}, "native allocation cases")
    counters = ("peak","requested","allocs","reallocs")
    deltas = {}
    for k in a:
        x, y = a[k], b[k]
        need(all(x[f] == y[f] for f in ("seed","live","decoded","fingerprint_bytes")), f"same ownership and source work {k}")
        d = {f:y[f]-x[f] for f in counters}
        if k.endswith(("absent", "zero")):
            need(all(v == 0 for v in d.values()), f"untouched negative control {k}")
        else:
            need(d["peak"] <= 0 and d["requested"] < 0
                 and d["allocs"]+d["reallocs"] < 0, f"strict no-peak-regression and traffic win {k}")
        deltas[k] = d
    inventory = {"jsonl-one":{"response","catalog"},"sqlite-one":{"response","catalog"},
                 "jsonl-torn":{"response","catalog"},"jsonl-broken":{"response"},
                 "jsonl-missing":{"response"},"jsonl-many":{"response"},"sqlite-many":{"response"}}
    hashes = {}
    for k, categories in inventory.items():
        for category in sorted(categories):
            left, right = ((pair/f"{k}-{arm}-{category}.bytes").read_bytes() for arm in bins)
            need(left == right and len(left) > 20, f"exact native byte parity {k} {category}")
            hashes[f"{k}-{category}"] = {"bytes":len(left),"sha256":sha(left)}
    return {"allocation":arms,"candidate_minus_stock":deltas,"same_fixture_bytes":hashes}

def trial(w,t,profile,feature,frozen=None):
    frozen = frozen or {}
    fl = [] if feature == "default" else ["--features", "serde_json/preserve_order"]
    graph = cargo(w,t,"stock","tree","-p","session-storage","-e","features","-i","serde_json",*fl,capture=True)
    need(("serde_json feature \"preserve_order\"" in graph) == bool(fl), "resolved serde_json layout")
    bins, tests = {}, {}
    for arm in ("stock","candidate"):
        bins[arm] = frozen.get(arm) or build(w,t,arm,profile,feature)
        out = execute(w,bins[arm],f"{profile}-{feature}-{arm}-full")
        status, = [ln for ln in out.splitlines() if ln.startswith("test result:")]
        need(status.startswith("test result: ok.") and int(status.split()[3]) == 98, "complete native suite")
        tests[arm] = status.split(";")[:-1]
    fingerprints = {k:sha(v.read_bytes()) for k,v in bins.items()}
    need(len(set(fingerprints.values())) == 2 and tests["stock"] == tests["candidate"],"distinct fresh leaves and matched native suite")
    return {"distinct_executable_sha256":fingerprints, "complete_suite":tests,
            "pairs":[execute_pair(w,bins,profile,feature,r) for r in range(2 if profile=="release" else 1)]}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for x in ("modules","core","work","toolchain-bin"):
        p.add_argument("--"+x,type=Path,required=True)
    p.add_argument("--archives",type=Path,required=True,action="append")
    p.add_argument("--use-existing-target",type=Path,help="Explicit build-only cache; every tested leaf is cleaned")
    p.add_argument("--use-existing-vendor",type=Path,help="Previously verified directory-source vendor")
    p.add_argument("--mode",choices=("screen","full"),default="full")
    args = p.parse_args()
    w,t = args.work.resolve(),args.toolchain_bin.resolve()
    stock,candidate = stage_native_inputs(args.modules,args.core,w,t,args.archives)
    if args.use_existing_target:
        dest = args.use_existing_target.resolve(strict=True)
        need(dest.is_dir() and dest.name == "target","explicit owned cargo target")
        (w/"target").rmdir()
        (w/"target").symlink_to(dest,target_is_directory=True)
    if args.use_existing_vendor:
        dest = args.use_existing_vendor.resolve(strict=True)
        oracle = w/"vendor"
        left = {p.relative_to(oracle):sha(p.read_bytes()) for p in oracle.rglob("*") if p.is_file()}
        right = {p.relative_to(dest):sha(p.read_bytes()) for d in oracle.iterdir()
                 for p in (dest/d.name).rglob("*") if p.is_file()}
        need(left == right and len(left) == 9520 + 157,"same independently verified vendor bytes")
        oracle.rename(w/"vendor-reference")
        (w/"vendor").symlink_to(dest,target_is_directory=True)
    composed = compose(w,stock)
    git_apply(w,candidate,"fallback")
    subprocess.run([t/"rustfmt","--check","--edition","2024","--config","skip_children=true",
                    candidate/SRC/"service/sessions.rs", HERE/"native.rs", HERE/"meter.rs"],
                   check=True, timeout=30)
    for arm in (stock,candidate):
        attach(arm)
    profiles = [("release","default")] if args.mode == "screen" else [
        (p,f) for f in ("default","preserve_order") for p in ("release","debug")]
    results = {f"{profile}-{feature}": trial(w,t,profile,feature) for profile,feature in profiles}
    seal(w, results, composed, "PASS" if args.mode == "full" else "SCREEN_PASS")

def seal(w, results, composed, status):
    receipt = {"status":status,
               "scope":"native session-storage service, JSONL and SQLite; not IPC/Desktop or process RAM",
               "source_inventory_sha256":sha((HERE/"source-files.json").read_bytes()),
               "lock_sha256":sha((HERE/"Cargo.lock").read_bytes()),"toolchain_sha256":TOOL_PINS,
               "source_patch_sha256":sha((HERE/"source.patch").read_bytes()),
               "composition_582_sha256":sha((HERE/"composition-582.patch").read_bytes()),
               "composition_source_only_apply_and_reverse_orders":2,
               "composition_source_only_blobs":composed,"profiles":results}
    (w/"verification.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(receipt["status"],flush=True)

if __name__=="__main__":
    main()
