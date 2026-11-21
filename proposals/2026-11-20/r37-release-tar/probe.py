"""Run against two reviewed scripts/release.py files. No product builds or invocations."""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace

MIB = 1024 * 1024
NAMES = ("Proteus-desktop", "Proteus-core", "Proteus-modules", "Proteus-desktop-extensions")


def git(root, *args):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args],
                          cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def fixture(root, n):
    root.mkdir()
    git(root, "init", "--quiet", "--template=")
    (root / ".gitignore").write_text("ignored\n")
    (root / "docs").mkdir()
    (root / "docs/committed").write_text("source %d\n" % n)
    (root / "docs/committed").chmod(0o755)
    (root / "link").symlink_to("docs/committed")
    (root / "payload").write_bytes(random.Random(n).randbytes(4 * MIB))
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=test@example.invalid",
        "commit", "--quiet", "-m", "synthetic fixture")
    (root / "docs/committed").write_text("dirty bytes, not from HEAD")
    (root / "ignored").write_text("not exported")
    (root / "untracked").write_text("also not exported")


def payload_inventory(path):
    with tarfile.open(path) as archive:
        items = []
        for m in archive:
            # The untracked wrapper directory sources/ receives a new timestamp
            # for each run. No claim of gzip-header or byte-for-byte tar identity.
            digest = hashlib.sha256(archive.extractfile(m).read()).hexdigest() if m.isfile() else None
            items.append((m.name, m.type, m.mode, m.linkname, digest, m.uid, m.gid, m.uname, m.gname, m.size))
        return items


def usage(paths):
    regular = [p.stat() for p in paths if not p.is_symlink() and p.is_file()]
    return dict(files=len(regular), logical=sum(s.st_size for s in regular),
                allocated=sum(s.st_blocks * 512 for s in regular))


def export(source_file, roots, target):
    stages = []
    workdirs = []
    def archive_command(args, cwd):
        assert args[:3] == ["git", "archive", "--format=tar"] and args[-1] == "HEAD", args
        parent = Path(args[args.index("-o") + 1]).parent
        if not workdirs:
            workdirs.append(parent)
        assert workdirs == [parent]
        git(cwd, *args[1:])

    @contextmanager
    def open_archive(path, *args, **kwargs):
        top = workdirs[0]
        def sample(when):
            stages.append(dict(when=when, snapshots=usage(top.glob("*.tar")),
                               extracted=usage((top / "sources").rglob("*")), output=usage([target])))
        if path == target:
            sample("before compression")
        with tarfile.open(path, *args, **kwargs) as archive:
            yield archive
        sample("after " + ("compression" if path == target else path.name))

    source = ast.parse(source_file.read_text())
    fn, = (n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "source_archive")
    env = dict(Path=Path, tempfile=tempfile, tarfile=SimpleNamespace(open=open_archive),
               ROOT=roots[0], run=archive_command)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source_file), "exec"), env)
    try:
        env["source_archive"](dict(zip(("harness", "modules", "extensions"), roots[1:])), target)
    finally:
        assert workdirs and not workdirs[0].exists(), "temporary staging was not cleaned up"
    return stages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--pinned", nargs=4, type=Path, metavar=("DESKTOP", "CORE", "MODULES", "EXTENSIONS"),
                        help="measure four exact shipping revisions as inert Git archive inputs")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="source-export-probe-") as td:
        root = Path(td)
        if args.pinned:
            roots = [p.resolve() for p in args.pinned]
            specs = json.loads(git(roots[0], "show", "HEAD:repositories.json").stdout)
            commits = [git(p, "rev-parse", "HEAD").stdout.decode().strip() for p in roots]
            assert commits == ["b6a7ec2d8d7e486c8aba01291aa8c89774c4cded",
                               *(specs[k]["rev"] for k in ("harness", "modules", "extensions"))]
            corpus = dict(commits=dict(zip(NAMES, commits)))
        else:
            roots = [root / n for n in NAMES]
            for i, repo in enumerate(roots):
                fixture(repo, i)
            corpus = dict(synthetic_mib=16)
        runs = {}
        inventories = []
        bad = root / "no commits"
        bad.mkdir()
        git(bad, "init", "--quiet", "--template=")
        for label, script in (("base", args.base), ("candidate", args.candidate)):
            target = root / label / "sources.tar.gz"
            target.parent.mkdir()
            stages = export(script, roots, target)
            inventories.append(payload_inventory(target))
            runs[label] = dict(stages=stages)
            if args.pinned:
                continue
            final = root / "previous artifact"
            final.write_bytes(b"old")
            try:
                export(script, [*roots[:-1], bad], final)
            except subprocess.CalledProcessError:
                assert final.read_bytes() == b"old"
            else:
                raise AssertionError("expected fourth Git export to fail")
        assert inventories[0] == inventories[1]
        rows = {r[0]: r for r in inventories[0]}
        for i, name in enumerate(NAMES):
            p = "sources/" + name + "/"
            assert any(k.startswith(p) for k in rows)
            if args.pinned:
                continue
            assert len(rows) == 1 + 6 * 4, list(rows)
            assert rows[p + "docs/committed"][4] == hashlib.sha256(("source %d\n" % i).encode()).hexdigest()
            assert rows[p + "docs/committed"][2] & 0o111
            assert rows[p + "link"][1:2] == (tarfile.SYMTYPE,) and rows[p + "link"][3] == "docs/committed"
            assert p + "ignored" not in rows and p + "untracked" not in rows
        counts = {kind: [s["snapshots"]["files"] for s in run["stages"]] for kind, run in runs.items()}
        assert counts == {"base": [1, 2, 3, 4, 4, 4], "candidate": [1, 1, 1, 1, 0, 0]}, counts
        for run in runs.values():
            run["peak"] = {m: max(sum(s[k][m] for k in ("snapshots", "extracted", "output"))
                                  for s in run["stages"]) for m in ("logical", "allocated")}
        print(json.dumps(dict(corpus=corpus, archive_entries=len(rows), runs=runs), indent=2))


if __name__ == "__main__":
    main()
