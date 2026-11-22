#!/usr/bin/env python3
"""Apply the exact 200 selected patches to four fresh local Git checkouts; no network/build."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMPONENTS = ("core", "modules", "desktop", "extensions")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update(GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="")


def need(ok, msg):
    if not ok:
        raise ValueError(msg)


def h256(b):
    return hashlib.sha256(b).hexdigest()


def git(root, *args, data=None):
    return subprocess.run(
        ["git", "--no-optional-locks", "-c", "protocol.allow=never", "-C", str(root), *args],
        env=ENV, input=data, stdout=subprocess.PIPE, check=True
    ).stdout


def file_bytes(p):
    need(p.is_file() and not p.is_symlink(), "Expected regular file: " + str(p))
    return p.read_bytes()


def tree(root):
    records = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if rel.parts[0] == ".git":
            continue
        if p.is_symlink():
            records.append([str(rel), "link", str(p.readlink())])
        elif p.is_file():
            records.append([str(rel), "x" if p.stat().st_mode & 0o111 else "-", h256(p.read_bytes())])
        else:
            need(p.is_dir(), "Unexpected nonregular source entry: " + str(p))
    return {"tree_sha256": h256(json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()),
            "entries": len(records), "cargo_lock_sha256": h256(file_bytes(root/"Cargo.lock"))}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--delivery", type=Path, required=True, help="local collector Git repository")
    cli.add_argument("--delivery-commit", required=True, help="full SHA of verified local delivery commit")
    for c in COMPONENTS:
        cli.add_argument("--"+c, type=Path, required=True, help="fresh detached local "+c+" checkout")
    cli.add_argument("--check-only", action="store_true", help="verify all 200 payloads and pinned worktrees without applying")
    opts = cli.parse_args()
    manifest = json.loads(file_bytes(HERE/"m200.json"))
    rows = manifest["patches"]
    need(manifest["exact_total"] == len(rows) == len({r["pr"] for r in rows})
         == len({r["sha256"] for r in rows}) == 200 and rows[-1]["pr"] == manifest["last_pr"] == 442,
         "Not the exact 200-row manifest")
    need([r["ordinal"] for r in rows] == list(range(1,201))
         and len({r["path"] for r in rows}) == 200, "Unexpected ordering or path collision")
    counts = Counter(r["component"] for r in rows)
    need(counts == {"core":38,"modules":56,"desktop":60,"extensions":46}, "Unexpected component counts")
    need(Counter(r["origin"] for r in rows)=={"collector-main":146,"pull-head":50,"local-variant":4},
         "Unexpected provenance counts")
    delivery = opts.delivery.resolve(strict=True)
    roots = {c:getattr(opts,c).resolve(strict=True) for c in COMPONENTS}
    distinct = [delivery,*roots.values()]
    need(len(set(distinct))==len(distinct) and not any(a!=b and a.is_relative_to(b) for a in distinct for b in distinct),
         "Use five distinct non-nested repositories")
    commit = opts.delivery_commit
    need(re.fullmatch(r"[0-9a-f]{40}",commit) is not None, "Supply the full verified delivery commit")
    need(git(delivery,"cat-file","-t",commit).strip()==b"commit", "Delivery commit absent locally")
    collector=manifest["collector"]; base=collector["base_commit"]
    need(git(delivery,"rev-parse",base+"^{tree}").decode().strip()==collector["base_tree"], "Wrong collector base")
    git(delivery,"merge-base","--is-ancestor",base,commit)
    for c,p in roots.items():
        pin=manifest["components"][c]["pin"]
        need(git(p,"rev-parse","--show-toplevel").decode().strip()==str(p)
             and git(p,"rev-parse","HEAD").decode().strip()==pin
             and git(p,"rev-parse","--abbrev-ref","HEAD").strip()==b"HEAD",
             f"{c}: use a fresh detached worktree at {pin}")
        need(git(p,"status","--porcelain=v1","--untracked-files=all","--ignored=matching")==b"",
             f"{c}: checkout is not empty of local edits/artifacts")
    sidecar, = manifest["unscored_test_sidecars"]
    need((sidecar["pr"],sidecar["component"],sidecar["after_ordinal"],sidecar["count"],sidecar["path"])==
         (247,"core",50,0,"local-variants/247-preserved-regressions.patch"), "Wrong historical test-only sidecar")
    preserved = file_bytes(HERE/sidecar["path"])
    need((len(preserved),h256(preserved),hashlib.sha1(f"blob {len(preserved)}\0".encode()+preserved).hexdigest())==
         (sidecar["bytes"],sidecar["sha256"],sidecar["git_blob_sha1"]), "Historical test sidecar drift")
    payload = {}
    earlier = {}
    for r in rows:
        n=r["pr"]; c=r["component"]; path=r["path"]
        need(all(d in earlier and earlier[d]==c for d in r["requires"]), f"#{n}: missing antecedent")
        if n>=393:
            chosen="cumulative" if n in (396,409,414,418,424,425,426,432) else "stock"
            need(r["selected_variant"]==chosen, f"#{n}: wrong selected overlay")
        if r["origin"]=="local-variant":
            p=HERE/path
            need(path.startswith("local-variants/") and p.resolve(strict=True).parent==HERE/"local-variants",
                 f"#{n}: bad embedded path")
            b=file_bytes(p)
        else:
            need(r["origin"] in ("collector-main","pull-head") and path.startswith("proposals/"),
                 f"#{n}: bad published path")
            # Every Git-hosted payload must be in the caller's explicit delivery commit.
            # Historical draft heads are provenance only: no fetch and no fallback.
            b=git(delivery,"cat-file","blob",commit+":"+path)
        blob=hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
        need((h256(b),blob,len(b))==(r["sha256"],r["git_blob_sha1"],r["bytes"]),
             f"#{n}: wrong SHA/size: {path}")
        payload[n]=b; earlier[n]=c
    print("Verified 200 selected payloads, one unscored test sidecar and four pinned clean checkouts; no changes yet.",
          file=sys.stderr,flush=True)
    if opts.check_only:
        return
    for r in rows:
        n=r["pr"]; c=r["component"]; p=roots[c]
        print(f'{r["ordinal"]:03}/200 #{n} {c} {r["selected_variant"]} {r["path"]}',file=sys.stderr,flush=True)
        git(p,"apply","--check","-",data=payload[n])
        git(p,"apply","-",data=payload[n])
        if r["ordinal"]==sidecar["after_ordinal"]:
            print("Unscored Core regression tests #247 (not a production change)",file=sys.stderr,flush=True)
            git(roots["core"],"apply","--check","-",data=preserved)
            git(roots["core"],"apply","-",data=preserved)
        if r["ordinal"]==150:
            for c in COMPONENTS:
                a=manifest["components"][c]; observed=tree(roots[c])
                need(observed=={"tree_sha256":a["m150_tree_sha256"],"entries":a["m150_entries"],
                                "cargo_lock_sha256":a["m150_lock_sha256"]},
                     f"{c}: exact M150 anchor did not reproduce; stop before overlays")
                print(json.dumps({"component":c,"checkpoint":"M150",**observed}),flush=True)
    for c in COMPONENTS:
        observed=tree(roots[c])
        expectation=manifest["known_final_source_checks"].get(c)
        if expectation is not None:
            need(all(expectation[k]==actual for k,actual in observed.items()),f"{c}: exact M200 source/lock differs")
        print(json.dumps({"component":c,"checkpoint":"M200","selected_patches":counts[c],
                          "matched_known_final_tree":expectation is not None,**observed}),flush=True)


if __name__=="__main__":
    try:
        main()
    except (ValueError,OSError,subprocess.CalledProcessError) as err:
        sys.exit(f"HOLD: {err}. No retry, conflict adjustment, commit, build, test or push performed by this tool.")
