"""Compile exact code excerpts and the actual diff parser with a recording text system.
Usage: python3 run.py /path/to/Desktop [candidate]
Needs cargo, rustc and already cached serde 1.0.228+derive. No GUI/Tree-sitter engine."""
import sys,subprocess,tempfile,shutil
from pathlib import Path
repo=Path(sys.argv[1]);here=Path(__file__).resolve().parent
ui=(repo/'src/ui/diff/mod.rs').read_text()
def body(s,start):
    a=s.index(start); b=s.index('{',a);depth=1
    while depth:
        b+=1;depth+=(s[b]=='{')-(s[b]=='}')
    return s[a:b+1]
frame=(here/'frame.rs').read_text()
tracked="syntax_revision: Option<u64>" in ui
# For a candidate exposing the optional generation read, compile the actual
# feature-selected body against a read-only test counter. There are no registrations.
if tracked:
    vendor=(repo/'vendor/gpui-component/src/highlighter/mod.rs').read_text()
    frame=frame.replace('@@REVISION@@','impl SyntaxHighlighter {'+body(vendor,'pub fn language_revision()')+'}')
else:
    frame=frame.replace('@@REVISION@@','impl SyntaxHighlighter { fn language_revision()->Option<u64>{Some(0)} }')
syntax=(repo/'src/ui/diff/syntax.rs').read_text()
for k,v in {'@@SET_PATCH@@':body(ui,'    pub fn set_patch('),
  '@@SYNTAX@@':syntax[syntax.index('pub(super) type Highlights'):syntax.index('pub(super) fn code(')],
  '@@RENDER_THEME@@':(ui[ui.index('        let revision = SyntaxHighlighter::language_revision();',ui.index('impl Render for DiffView')):ui.index('        let font = Font {',ui.index('impl Render for DiffView'))] if tracked else body(ui,'        if !std::sync::Arc::ptr_eq')),
  '@@WIDTHS@@':ui[ui.index('            let widths = self'):ui.index('            self.measured = Some((font.clone()')]
 }.items(): frame=frame.replace(k,v)
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);src=root/'src';src.mkdir();(src/'diff').mkdir()
    for infile,out in [('lib.rs','mod.rs'),('parse.rs','parse.rs')]:shutil.copyfile(repo/'crates/diff/src'/infile,src/'diff'/out)
    (src/'main.rs').write_text(frame);shutil.copyfile(here/'normal.diff',src/'normal.diff')
    (root/'Cargo.toml').write_text('[package]\nname="diff-display-check"\nversion="0.0.0"\nedition="2024"\n[features]\ndefault=["tree-sitter"]\ntree-sitter=[]\n[dependencies]\nserde={version="=1.0.228",features=["derive"]}\n')
    subprocess.run(['cargo','run','--offline','--quiet',*(['--no-default-features'] if 'untracked' in sys.argv[2:] else []),'--',*sys.argv[2:]],cwd=root,check=True)
