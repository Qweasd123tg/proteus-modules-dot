from pathlib import Path
import tempfile,argparse,subprocess
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args()
d=a.desktop/'src/ui/tabs';s=(d/'arrange.rs').read_text();cand='struct TabArrangement(' in s
bar=(d/'bar.rs').read_text()
before=s.index('const REACH_Y');src='use std::collections::HashMap;\nuse std::cell::RefCell;\n'+('use std::rc::Rc;\n' if cand else '')+s[before:]
src=src.replace('pub(in crate::ui) struct TabArrangement','pub(super) struct TabArrangement')
if cand:
 assert 'arrange::frame(&self.tab_arrangement' in bar and 'arrange::record(&arrangement' in bar and '&this.tab_arrangement' in bar
 assert bar.count('self.tab_arrangement.clone()')==2
 assert 'tab_arrangement: Default::default()' in (a.desktop/'src/ui/workspace.rs').read_text()
 assert 'layout.contains(id)' in s
b='' if not cand else '''pub(super) fn lifetime() {
 use std::rc::Rc;
 let root=TabArrangement::default();let sentinel=Rc::downgrade(&root.0);
 let capture=root.clone();
 for i in 0..64 {record(&root,&format!("old-{i}"),Default::default())}
 assert_eq!(root.0.borrow().bounds.len(),64);
 drop(root);assert!(sentinel.upgrade().is_some());
 drop(capture);assert!(sentinel.upgrade().is_none());println!("64 stale idle bounds survive while owner lives; after the owner and outstanding callback clone drop the weak sentinel expires.");
}'''
tpl=(Path(__file__).with_name('peer.rs.in').read_text().replace('/*SOURCE*/',src).replace('/*BOUNDARY*/',b).replace('/*A*/','&h,' if cand else '').replace('/*B*/','&k,' if cand else '').replace('/*NEW*/','TabArrangement::default()' if cand else '()').replace('/*LIFETIME*/','lifetime();' if cand else '').replace('/*RESET*/','assert_eq!(drop_before(&h,&pane,"source"),None);' if cand else ''))
with tempfile.TemporaryDirectory() as t:
 t=Path(t);f=t/'replay.rs';f.write_text(tpl);subprocess.run([a.rustc,'--edition=2024','--cfg','candidate' if cand else 'baseline',str(f),'-o',str(t/'test')],check=True);subprocess.run([str(t/'test')],check=True)
