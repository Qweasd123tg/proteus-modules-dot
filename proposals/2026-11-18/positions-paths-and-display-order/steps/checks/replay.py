#!/usr/bin/env python3
"""Usage: python replay.py BEFORE AFTER EXTENSIONS_TREE RUSTC DEPS
BEFORE/AFTER: Desktop checkout or directories containing steps.rs, view.rs.
EXTENSIONS_TREE: checkout, or its bare upstream git repository. No Cargo, network, app, actual settings or providers.
DEPS: directory containing compatible prebuilt serde_json Rust rlib and dependencies.
"""
from pathlib import Path
import re,sys,subprocess,tempfile
before,after,ext=map(Path,sys.argv[1:4]);rustc=sys.argv[4];deps=Path(sys.argv[5]);here=Path(__file__).resolve().parent
def upstream(path):
    return (ext/path).read_text() if (ext/path).is_file() else subprocess.check_output(['git','--git-dir='+str(ext),'show','ef064381:'+path],text=True)
def ui(root,name):
    p=root/'src/ui/extensions/declarative'/name
    return (p if p.exists() else root/name).read_text()
def fn(s,needle):
    i=s.index(needle); start=s.rfind('\n',0,i)+1; tab=re.match(r'[ \t]*', s[start:]).group()
    return s[start:s.index('\n'+tab+'}',i)+len(tab)+2]
def section(s,left,right):
    a=s.index(left);return s[a:s.index(right,a)]
settings=upstream('packages/model/src/settings.rs');popup=upstream('packages/model/src/popup.rs');main=upstream('packages/model/src/main.rs')
effort=fn(settings,'pub fn efforts(')
emit=section(popup,'let options: Vec<&Value> = efforts.iter()', ']);').split('rows.extend([')
expr=emit[1][emit[1].index('json!('):].strip().rstrip(',')
receive=section(main,'let chosen = value\n                    .as_u64()', 'if let Some(chosen)')
assert 'Surface::Popup => {' in main and 'let root = popup::render(host, self.models_open);' in main
assert 'let stepper = efforts.len() >= 2;' in popup and 'if stepper {' in popup
def translate(tree):
    s=ui(tree,'steps.rs');v=ui(tree,'view.rs')
    rs=(here/'frame.rs.in').read_text()
    update=section(v,'stepper.update(cx, |stepper, cx| {','});').split('{',1)[1]
    keys=['pub fn new(', 'fn scrub_to(', 'fn finish_scrub(', 'pub(super) fn step(']
    if 'fn sync_options(' in s:keys.append('pub(super) fn sync_options(')
    methods='\n'.join(fn(s,k).replace('pub(super) fn','fn') for k in keys)
    down=section(s,'let step = nearest(this.track.get(), count, event.position.x);','                });')
    down=re.search(r'let step = nearest\(this.track.get\(\), count, event.position.x\);\s*this.scrub_to\(step, cx\);',down).group().replace('event.position.x','x')
    move=section(s,'if this.scrub.is_some() {','\n                    });').replace('event.position.x','x')
    shown=section(s,'let shown = self',';')+';';shown=shown.replace('let shown =','let shown:usize =')
    assert v.index('self.prune_fields(&root);')<v.index('self.prepare_steps(&root, cx);')
    assert 'let _ = release.update(cx, |this, cx| this.finish_scrub(cx));' in s
    for hook in ['.on_mouse_up(MouseButton::Left, finish.clone())','.on_mouse_up_out(MouseButton::Left, finish)']: assert hook in s
    for k,val in [('METHODS',methods),('NEAREST',fn(s,'fn nearest(')),('CENTER',fn(s,'fn center(')),('SHOW',shown),('DOWN',down),('MOVE',move),('UPDATE',update),('EFFORTS',effort),('EMIT',emit[0]+'\n'+expr),('RECEIVE',receive)]:
        rs=rs.replace('__'+k+'__',val)
    if 'fn refreshed_options_invalidate_' in s:
        rs+='\n#[cfg(test)] mod in_tree_regression { use super::*; #[::core::prelude::v1::test]\n'+fn(s,'fn refreshed_options_invalidate_')+'\n}\n'
    return rs
with tempfile.TemporaryDirectory() as td:
    p=Path(td); f=p/'test.rs'; out=p/'test'
    dep,=deps.glob('libserde_json-*.rlib')
    for mode,tree in [('before',before),('after',after)]:
        f.write_text(translate(tree))
        subprocess.run([rustc,'--edition=2024','-L','dependency='+str(deps),'--extern','serde_json='+str(dep),str(f),'-o',str(out)],check=True)
        subprocess.run([str(out),mode],check=True)
        if mode=='after':
            test=p/'native_test'
            subprocess.run([rustc,'--test','--edition=2024','-L','dependency='+str(deps),'--extern','serde_json='+str(dep),str(f),'-o',str(test)],check=True)
            subprocess.run([str(test)],check=True)
