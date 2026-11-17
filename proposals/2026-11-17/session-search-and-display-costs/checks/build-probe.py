"""Emit a small Rust probe for the real picker matching() in two Desktop source trees."""
from pathlib import Path
import sys
if len(sys.argv)!=4:
    raise SystemExit("usage: python3 build-probe.py BASE_DESKTOP PATCHED_DESKTOP EMPTY_OUT_DIRECTORY")
old,new,out=map(Path,sys.argv[1:])
def src(root):
    return (root / 'src/ui/picker.rs').read_text()
def matching(s):
    start=s.index('fn matching<T>(')
    return s[start:s.index('\n}\n',start)+2]
s=src(old);start=s.index('#[derive(Clone, PartialEq)]\npub(super) struct Choice<T>')
choice=s[start:s.index('\n}\n',start)+2].replace('pub(super) struct Choice','struct Choice')
out.mkdir(exist_ok=True,parents=True)
template=Path(__file__).with_name('picker-gate.rs').read_text()
with (out/'main.rs').open('x') as f:
    f.write(template.replace('__CHOICE__',choice).replace('__OLD__',matching(s)).replace('__NEW__',matching(src(new))))
with (out/'Cargo.toml').open('x') as f:
    f.write("""[package]
name = "proteus-picker-probe"
version = "0.1.0"
edition = "2024"
publish = false
[[bin]]
name = "picker-probe"
path = "main.rs"
[dependencies]
gpui_shared_string = { package = "gpui-pre-shared-string", version = "=0.3.10" }
smol_str = "=0.3.6"
""")
