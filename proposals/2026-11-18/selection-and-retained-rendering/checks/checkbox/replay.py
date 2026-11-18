#!/usr/bin/env python3
"""Red/green probe; reads two files from a local pinned Git revision, writes only to a temporary directory."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REV = "2307e9c67125bbe66f15ced51317a2dfcc437aa4"
PATCH_SHA = "d3067bc15413dcc249c201cfcffe6d0f2fd53ecefa5aa8e996debe47155bd8d4"
PATH = Path("src/ui/settings/fields.rs")
BASE = "e038818a96da61e8ce5e52a8b66ce513cbf37e20"
AFTER = "ab5856dbc3863f1fd3517435e2d826450f03ef2e"

def method(source, name):
    # Match standalone named functions, preserving the original body verbatim.
    m = re.search(r"(?m)^ *(?:pub(?:\([^)]*\))? )?fn " + name + r"\s*\(", source)
    if not m:
        raise ValueError(name)
    op = source.index("{", m.end())
    depth = 1
    for i in range(op + 1, len(source)):
        depth += (source[i] == "{") - (source[i] == "}")
        if depth == 0:
            return source[m.start():i+1] + "\n"
    raise ValueError(name)

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def run():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--desktop", type=Path, required=True, help="Local checkout or bare Git repository containing the pinned commit")
    p.add_argument("--serde-json", type=Path, required=True, help="Rust-compatible libserde_json-*.rlib; transitive dependencies in its directory")
    p.add_argument("--rustc", default=os.environ.get("RUSTC", "rustc"), help="Rust compiler that built the rlib")
    p.add_argument("--patch", type=Path, default=HERE.parent / "checkbox-restore.patch")
    a = p.parse_args()
    rlib = a.serde_json.resolve(strict=True)
    patch = a.patch.resolve(strict=True)
    if hashlib.sha256(patch.read_bytes()).hexdigest() != PATCH_SHA:
        raise ValueError("patch SHA256 mismatch")
    def source(path):
        return subprocess.check_output(["git", "-C", str(a.desktop), "show", REV + ":" + str(path)])
    b = source(PATH)
    if git_blob(b) != BASE:
        raise ValueError("source blob mismatch")
    d = source("src/settings/draft.rs").decode()
    # Verify the actual discriminator and precedence, not only the isolated checkbox handler.
    fields = b.decode()
    assert "let tagged = super::tags::is_tag_field(field);" in fields
    assert "let control = if tagged {\n            self.string_tags(&spec, cx)\n        } else {\n            match kind {" in fields
    assert "FieldKind::MultiChoice(options) => multi_choice(&spec, options)," in fields
    schema = source("src/settings/schema.rs").decode()
    assert "ConfigValueSchema::Array { items } => match items.as_ref() {\n            ConfigValueSchema::Enum { options } => FieldKind::MultiChoice(options)," in schema
    tag_source = source("src/ui/settings/tags.rs").decode()
    skeleton = (HERE / "frame.rs").read_text().replace("//TAG_RULE", method(tag_source,"is_tag_field"))
    with tempfile.TemporaryDirectory() as td:
        work = Path(td).resolve()
        (work / PATH).parent.mkdir(parents=True)
        (work / PATH).write_bytes(b)
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=work, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=work, check=True)
        subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=work, check=True)
        result = (work / PATH).read_bytes()
        if git_blob(result) != AFTER:
            raise ValueError("after-patch blob mismatch")
        for mode, data in (("before", b), ("after", result)):
            s = data.decode()
            start = s.index("                    let next: Vec<Value> = options", s.index("fn multi_choice"))
            click = s[start:s.index("                }),", start)]
            draft_methods = "".join(method(d, n) for n in ("value", "set_value", "edit_value", "module_config"))
            draft_helpers = "".join(method(d, n) for n in ("remove_nested", "ensure_object", "is_empty_object"))
            setters = method(s, "set")
            if mode == "after":
                setters += method(s, "set_choices")
            body = skeleton.replace("//DRAFT", draft_methods).replace("//UTIL", draft_helpers).replace("//METHODS", setters).replace("//HELPER", method(s, "checkbox_value") if mode == "after" else "").replace("//CLICK", click)
            src = work / (mode + ".rs")
            src.write_text(body)
            exe = work / mode
            subprocess.run([a.rustc, "--edition=2024", "-Awarnings", "-L", "dependency=" + str(rlib.parent), "--extern", "serde_json=" + str(rlib), str(src), "-o", str(exe)], check=True)
            got = subprocess.run([str(exe)], capture_output=True, text=True)
            expected = (588, 1) if mode == "before" else (0, 0)
            wanted = f"780 two-click cycles; {expected[0]} do not restore original draft"
            if got.returncode != expected[1] or got.stdout.strip() != wanted:
                raise RuntimeError(f"{mode}: unexpected {got.returncode}: {got.stdout} {got.stderr}")
            print(f"{mode}: {got.stdout.strip()}")
    print("Pinned dispatch and native tag predicate: four string values -> tag editor; four numeric values or mixed string/number -> checkbox handler.")
    print("Pinned source, patch application and reverse applicability verified. No GUI, service or profile was run.")

if __name__ == "__main__":
    run()
