"""Check full patch against pinned paths in a fresh directory, then verify opt-in routing."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path
here=Path(__file__).resolve().parent
src=Path(sys.argv[1]).resolve()
blob=lambda b: hashlib.sha1(f'blob {len(b)}\0'.encode()+b).hexdigest()
manifest=json.loads((here/'blobs.json').read_text())
with tempfile.TemporaryDirectory() as t:
 d=Path(t)
 for f,h in manifest['pinned'].items():
  b=(src/f).read_bytes(); assert blob(b)==h,(f,blob(b))
  dest=d/f; dest.parent.mkdir(exist_ok=True,parents=True); dest.write_bytes(b)
 subprocess.run(['git','init','-q'],cwd=d,check=True)
 patch=here/'defer-rich-text-only.patch'
 subprocess.run(['git','apply','--check',patch],cwd=d,check=True)
 subprocess.run(['git','apply',patch],cwd=d,check=True)
 for f,h in manifest['scoped'].items(): assert blob((d/f).read_bytes())==h
 state=(d/'vendor/gpui-base/src/text/state.rs').read_text()
 assert state.count('Self::new(TextViewFormat::Html, text, true, cx)')==1
 assert state.count('Self::new(TextViewFormat::Html, text, false, cx)')==1
 assert state.count('Self::new(TextViewFormat::Markdown, text, false, cx)')==1
 assert state.count('if self.defer_html_baseline')==1
 assert state.count('update_options.mode = ParseMode::DeferHtmlBaseline;')==1
 host=(d/'src/ui/extensions/declarative/rich_text.rs').read_text()
 assert 'TextViewState::html_for_replacements(html, cx)' in host and 'state.set_text(html, cx)' in host and '.push_str(' not in host
 print('verified 3 pinned and 3 patched Git blobs; default constructors eager, retained Desktop RichText opts in')
