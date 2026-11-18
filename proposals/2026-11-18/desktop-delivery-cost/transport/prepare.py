"""Prepare the local no-window runner from pinned Desktop and gpui-kit-assets sources."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

MODULES = "control graph lanes list manifest presentation process protocol session svg tree widget".split()
CARGO = '''[package]
name="desktop-transport-probe"
version="0.1.0"
edition="2024"
[dependencies]
proteus-diff={path="diff"}
proteus-contracts={git="https://github.com/Proteus-harness/Proteus-core.git",rev="105f8253f43a62b0f5025d99e2d4ccdcb322e34c"}
serde={version="1",features=["derive"]}
serde_json="1"
async-channel="2"
futures-lite="2"
libc="0.2"
anyhow="1"
roxmltree="0.21"
sha2="0.10"
'''


def blob(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def prepare(desktop, assets, out):
    source = desktop.resolve()
    folder = out / "src/declarative"
    folder.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in [m + ".rs" for m in MODULES] + ["process/budget.rs", "process/io.rs"]:
        destination = folder / name
        destination.parent.mkdir(exist_ok=True)
        original = source / "src/declarative" / name
        shutil.copyfile(original, destination)
        hashes[str(original.relative_to(source))] = blob(original)
    expected = json.loads(Path(__file__).with_name("blobs.json").read_text())
    if hashes != expected:
        raise ValueError("The Desktop blobs do not match this report's pinned sources")
    (out / "blobs.json").write_text(json.dumps(hashes, indent=2) + "\n")
    modules = "\n".join("pub mod " + mod + ";" for mod in MODULES + ["icons"])
    (folder / "mod.rs").write_text(modules + "\n")

    # Never used by the measured RichText. Use the icon names that the pinned
    # gpui-kit-assets 0.8.1/build.rs accepts when checking other stock views.
    names = sorted(path.stem for path in (assets / "assets/icons").glob("*.svg"))
    assert len(names) > 1000
    (folder / "icons.rs").write_text(
        "static NAMES:&[&str]=&" + json.dumps(names) + ";\n"
        "pub fn lucide(name:&str)->Option<()> { NAMES.binary_search(&name).ok().map(|_|()) }\n"
    )

    preferences = (source / "src/preferences.rs").read_text()
    start = preferences.index("pub enum BadgePlace")
    end = preferences.index("\n}", preferences.index("impl BadgePlace", start)) + 2
    (out / "src/preferences.rs").write_text(
        '#[derive(Clone,Copy,Debug,PartialEq,serde::Deserialize)]\n'
        '#[serde(rename_all="snake_case")]\n'
        + preferences[start:end] + "\npub fn config_dir()->Option<std::path::PathBuf>{None}\n"
    )
    shutil.copytree(source / "crates/diff", out / "diff", dirs_exist_ok=True)
    (out / "Cargo.toml").write_text(CARGO)
    shutil.copyfile(Path(__file__).with_name("Cargo.lock"), out / "Cargo.lock")
    shutil.copyfile(Path(__file__).with_name("main.rs"), out / "src/main.rs")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("assets", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    prepare(args.desktop, args.assets, args.out.resolve())
