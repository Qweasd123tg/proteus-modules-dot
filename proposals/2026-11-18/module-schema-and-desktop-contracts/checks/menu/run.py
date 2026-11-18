#!/usr/bin/env python3
"""python3 run.py DESKTOP_ROOT [RUSTC]. No Cargo or project build script."""
import re,sys,tempfile,subprocess
from pathlib import Path
here=Path(__file__).resolve().parent;root=Path(sys.argv[1])
def read(p):return (root/p).read_text()
def method(src,n):
    m=re.search(r'(?m)^    (?:pub(?:\(super\))? )?fn '+n+r'\(',src)
    return src[m.start():src.index('\n    }',m.start())+6]
layout,pane,tree,pins=[read('crates/tabs/src/'+f+'.rs') for f in ['layout','pane','tree','pins']]
menu=read('src/ui/tabs/menu.rs');s=(here/'main.rs.in').read_text()
s=s.replace('@layout@','\n'.join(method(layout,n) for n in ['panes','pane','pane_of','contains','can_split'])+'\n'+'\n'.join(method(pins,n) for n in ['others','right_of'] + (['unpinned_neighbors','close_availability'] if 'fn unpinned_neighbors(' in pins else ['unpinned_around'])))
s=s.replace('@tree@',method(tree,'panes')+'\n'+tree[tree.index("    fn collect<'a>"):tree.index('    pub(super) fn pane_mut')]).replace('@pane@',method(pane,'position')+'\n'+method(pane,'has'))
s=s.replace('@new@',method(menu,'new'))
tab=read('src/ui/tabs/tab.rs');bar=read('src/ui/tabs/bar.rs')
assert tab.index('menu::TabMenu::new(')<tab.index('.right_click_menu(') and 'strip_tab(pane, tab' in bar
assert 'item("Закрыть другие", self.has_others' in menu or 'self.has_others,' in menu
assert 'self.has_right,' in menu
with tempfile.TemporaryDirectory() as d:
    d=Path(d);f=d/'main.rs';f.write_text(s);subprocess.run([sys.argv[2] if len(sys.argv)>2 else 'rustc','--edition=2024','-O',str(f),'-o',str(d/'check')],check=True);subprocess.run([str(d/'check')],check=True)
