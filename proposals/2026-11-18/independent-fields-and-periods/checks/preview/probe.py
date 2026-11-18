#!/usr/bin/env python3
"""Source probe. Run on Desktop worktree (use --bare OVERLAY for a bare base)."""
from pathlib import Path
import argparse, os, re, shutil, subprocess as sp, tempfile
A=argparse.ArgumentParser()
A.add_argument("desktop",type=Path); A.add_argument("deps",type=Path,help="Cargo deps with anyhow, serde(derive), serde_json")
A.add_argument("--bare",metavar="OVERLAY",type=Path); A.add_argument("--expect",choices=['before','after'],required=True)
a=A.parse_args()
def read(p):
 if a.bare is None: return (a.desktop/p).read_text()
 if (a.bare/p).is_file(): return (a.bare/p).read_text()
 return sp.check_output(['git','--git-dir='+str(a.desktop),'show','HEAD:'+p]).decode()
U='src/ui/extensions/declarative/'
f,t,r,v=[read(U+p+'.rs') for p in ['fields','fields/textarea','render','view']]
fmt=read('src/ui/format.rs')
def capture(pattern,text):
 matches=re.findall(pattern,text,re.S); assert len(matches)==1,pattern
 return matches[0]
def block(src,marker):
 start=src.index(marker); first=src.index('{',start); n=1
 for j in range(first+1,len(src)):
  n+=int(src[j]=='{')-int(src[j]=='}')
  if n==0: return src[start:j+1]
 raise AssertionError(marker)
actual_new='fn set_input_preview' in f
assert actual_new==(a.expect=='after')
open_read=capture(r'(    let (?:id = disclosure_id\(id\);\s*let )?open = view\s*\.fields.*?;)',t)
# Collect the real state mutation, not the GPUI animation/notification calls.
click=capture(r'emit\(WillResize\);\s*(view\s*\.fields.*?;)\s*motion::toggled\(toggle',t)
keyboard=capture(r'emit\(WillResize\);\s*(view\s*\.fields.*?;)\s*motion::toggled\(keyboard',t[t.index('.on_key_down'):])
edit=capture(r'if grow && textarea::preview\(&state.read\(cx\).value\(\)\).is_some\(\) \{\s*(this\s*\.fields.*?;)',f)
explicit_prepare=capture(r'(self.fields.disclosures.entry\(id.clone\(\)\).or_insert\(\*open\);)',f)
explicit_read=capture(r'let opened = (self.fields.disclosures.*?);',r)
explicit_click=capture(r'emit\(super::view::WillResize\);\s*(this.fields.disclosures.*?;)',r)
assert 'if self.fields.disclosures.get(id).copied().unwrap_or(*open) => children.as_slice()' in v
assert 'self.prune_fields(&root);' in v and 'self.prepare_fields(&root, window, cx);' in v
assert 'self.prepare_fields_in(control, true, window, cx)' in f and 'let grow = settings && *lines > 1;' in f
assert 'if !open' in t and '"enter" | "space"' in t and 'editor_preview(state.read(cx).text().chars())' in t
click_id='id.to_owned()' if actual_new else 'textarea::disclosure_id(id)'
assert ('(key.clone(), id.to_owned())' if actual_new else '(key.clone(), id.clone())') in t
preview_default=capture(r'(preview_open: false,)',f) if actual_new else ''
src=(Path(__file__).parent/'frame.rs.in').read_text()
subs=dict(READ=open_read,CLICK=click,KEY=keyboard,EDIT=edit,DISCINIT=explicit_prepare,DISCREAD=explicit_read,DISCCLICK=explicit_click,PRUNE=block(f,'pub(super) fn prune_fields').replace('pub(super) fn','fn'),HELPER=block(f,'impl Fields {') if actual_new else '',IDHELPER=block(t,'pub(super) fn disclosure_id') if not actual_new else '',OPENFLAG='preview_open: bool,' if actual_new else '',INIT=preview_default,KEYID=click_id,PREVIEW=fmt[fmt.index('const PREVIEW_LINES:'):fmt.index('const MONTHS:')])
for k,val in subs.items(): assert '<'+k+'>' in src; src=src.replace('<'+k+'>',val)
with tempfile.TemporaryDirectory() as tmp:
 d=Path(tmp); (d/'probe.rs').write_text(src)
 for name in ['widget','graph','lanes','list','tree','control']: (d/(name+'.rs')).write_text(read('src/declarative/'+name+'.rs'))
 deps=a.deps.resolve(); cmd=[os.environ.get('RUSTC','rustc'),'--edition=2024','-Awarnings',str(d/'probe.rs'),'-o',str(d/'probe'),'-L','dependency='+str(deps)]
 for name in ['serde','serde_json','anyhow']:
  found=sorted(deps.glob('lib'+name+'-*.rlib')); assert len(found)==1,(name,found); cmd+=['--extern',name+'='+str(found[0])]
 sp.run(cmd,check=True); sp.run([str(d/'probe'),a.expect],check=True)
