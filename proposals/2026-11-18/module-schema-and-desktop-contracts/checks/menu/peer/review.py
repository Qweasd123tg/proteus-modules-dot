"""Review the actual availability & collector methods, counting cloned tab identities, not all heap operations."""
from pathlib import Path
import argparse,subprocess as sp,tempfile
p=argparse.ArgumentParser();p.add_argument('tree',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
def fn(s,n):
 i=s.index('fn '+n+'(');return s[i:s.index('\n    }',i)+6]
pins=(a.tree/'crates/tabs/src/pins.rs').read_text();menu=(a.tree/'src/ui/tabs/menu.rs').read_text();tab=(a.tree/'src/ui/tabs/tab.rs').read_text()
modern='fn close_availability(' in pins
assert tab.index('let menu = menu::TabMenu::new')<tab.index('.right_click_menu(')
m=fn(menu,'new')
assert ('layout.close_availability(id)' in m) if modern else ('!layout.others(id).is_empty()' in m and '!layout.right_of(id).is_empty()' in m)
for n in ['set_pinned','close_others','close_right','close_all']:assert 'fn '+n+'(' in pins
fun='\n'.join(fn(pins,n) for n in (['others','right_of','close_availability','unpinned_neighbors'] if modern else ['others','right_of','unpinned_around']))
code=Path(__file__).with_name('matrix.rs.in').read_text().replace('@@FUN@@',fun).replace('@@BEFORE@@',str(not modern).lower()).replace('@@FLAGS@@','self.close_availability(id)' if modern else '(!self.others(id).is_empty(),!self.right_of(id).is_empty())')
with tempfile.TemporaryDirectory() as t:
 t=Path(t);f=t/'gate.rs';f.write_text(code);sp.run([a.rustc,'--edition=2024','-Awarnings','-O',f,'-o',t/'gate'],check=True);sp.run([t/'gate'],check=True)
