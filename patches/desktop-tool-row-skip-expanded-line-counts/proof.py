"""Check the exact folds, formatter compositions, and logical traversal counts."""
import hashlib
import itertools
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

from lift import lift


packet = Path(__file__).resolve().parent
row = Path("src/ui/chat/tool_row.rs")
fmt = Path("src/ui/format.rs")
stock_row = "34e0491f2fb1dfc570d973a7cf4270ab9528892e"
post_row = "9255c753590bacbfd09969ea19179106f5585bdb"
fmt_states = {
    (): "c601492c839803744897377d0d4dc93466cd9856",
    (542,): "29d746781562b083b8f3a61dc430b26a11969454",
    (546,): "1fa829601fd244557eb89dc359c1c128ad2f0167",
    (542, 546): "2ff731375d0a76ccc9bc123cc47a9c80a43ef5d3",
}
composition_patch_sha256 = {
    542: "7e51eef5e4abc0f17458261466a409131ee77d78c14b74ad8d56bb430fa81f07",
    546: "59654e5acbeeffa1d39329b7c93288be39c10a5633b207eed0391d9ca402ad9b",
}


def blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def run(*command, cwd=None):
    result = subprocess.run(list(map(str, command)), check=True, text=True, cwd=cwd,
                            stdout=subprocess.PIPE)
    return result.stdout.strip()


def apply(patch, dest, *, reverse=False):
    direction = ["--reverse"] if reverse else []
    run("git", "apply", *direction, "--check", patch, cwd=dest)
    run("git", "apply", *direction, patch, cwd=dest)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def prepare(dest, source):
    for file in [row, fmt]:
        out = dest / file
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / file, out)
        out.chmod(0o644)


def test_orders(work, source):
    patches = {
        542: packet / "composition-542.patch",
        546: packet / "composition-546.patch",
        270: packet / "source.patch",
    }
    for index, order in enumerate(itertools.permutations(patches)):
        dest = work / f"order-{index}"
        prepare(dest, source)
        active = set()

        def check():
            assert blob(dest / row) == (post_row if 270 in active else stock_row)
            assert blob(dest / fmt) == fmt_states[tuple(sorted(active - {270}))]
            assert mode(dest / row) == mode(dest / fmt) == 0o644

        check()
        for step in order:
            apply(patches[step], dest)
            active.add(step)
            check()
        for step in reversed(order):
            apply(patches[step], dest, reverse=True)
            active.remove(step)
            check()
        for file in [row, fmt]:
            assert (dest / file).read_bytes() == (source / file).read_bytes()
    print("composition: all six orders and all intermediate subsets round-trip exactly")


def main():
    source, rustc, rustfmt = map(lambda arg: Path(arg).resolve(), sys.argv[1:])
    version = run(rustc, "--version")
    assert "rustc 1.95.0 " in version, version
    print(version)
    for rel, expected in [(row, stock_row), (fmt, fmt_states[()])]:
        assert blob(source / rel) == expected
        print(f"{expected} stock {rel}")
    for number, expected in composition_patch_sha256.items():
        path = packet / f"composition-{number}.patch"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
        print(f"{expected} #{number} patch sha256")
    cases = (packet / "cases.rs").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="proteus-fold-proof-") as scratch:
        work = Path(scratch)
        test_orders(work, source)
        all_results = []
        for composition, fmt_hash in fmt_states.items():
            name = "stock" if not composition else "+".join(map(str, composition))
            dest = work / name
            prepare(dest, source)
            for number in composition:
                apply(packet / f"composition-{number}.patch", dest)
            assert blob(dest / fmt) == fmt_hash
            patch = packet / "source.patch"
            apply(patch, dest)
            assert blob(dest / row) == post_row and blob(dest / fmt) == fmt_hash
            assert mode(dest / row) == mode(dest / fmt) == 0o644
            run(rustfmt, "--check", "--edition", 2024, "--config", "skip_children=true", dest / row)
            harness = dest / "harness.rs"
            lift((source / row).read_text(encoding="utf-8"), (dest / row).read_text(encoding="utf-8"),
                 (dest / fmt).read_text(encoding="utf-8"), cases, harness)
            print(f"{name}: fmt {fmt_hash}; row {post_row}; apply and rustfmt OK")
            for profile in (0, 3):
                exe = dest / f"proof-{profile}"
                run(rustc, "--edition=2024", "-C", f"opt-level={profile}", harness, "-o", exe)
                result = run(exe)
                assert result.startswith("paired projections: exhaustive="), result
                all_results.append(result)
                print(f"{name} opt-level={profile}\n{result}")
            apply(patch, dest, reverse=True)
            assert (dest / row).read_bytes() == (source / row).read_bytes()
            assert blob(dest / fmt) == fmt_hash
            for number in reversed(composition):
                apply(packet / f"composition-{number}.patch", dest, reverse=True)
            assert (dest / fmt).read_bytes() == (source / fmt).read_bytes()
            assert mode(dest / row) == mode(dest / fmt) == 0o644
            print(f"{name}: reverse restores both exact blobs and modes")
        assert all(result == all_results[0] for result in all_results)


if __name__ == "__main__":
    main()
