from pathlib import Path
def between(s,a,b):
 assert s.count(a)==1,a
 i=s.index(a);return s[i:s.index(b,i)]
def lift(s,d,pack):
 d.mkdir(parents=True,exist_ok=True)
 cosmic=s['vendor/gpui-fast-wgpu/src/cosmic_text_system.rs']
 query=between(cosmic,'    fn all_font_names(&self) -> Vec<String> {','    fn font_id(&self')
 fast=s['vendor/gpui-fast/src/text_system.rs']
 names=between(fast,'    pub fn all_font_names(&self) -> Vec<String> {','    /// Add a font\'s data')
 component=s['vendor/gpui-component/src/theme/mono_font.rs']
 desktop=s['src/ui/theme/fonts.rs']
 ss=s['witness/gpui_shared_string.rs']
 shared=between(ss,'#[derive(Eq, PartialEq, PartialOrd, Ord, Hash, Clone)]','impl JsonSchema for SharedString')
 shared+=between(ss,'impl From<String> for SharedString','impl From<Box<str>>')
 shared=shared.replace('pub struct SharedString(SmolStr);','pub struct SharedString(SmolStr);')
 
 x=between(desktop,'    let mut installed: Vec<SharedString> =','    let default_interface =')
 # Execute the two actual inventory request projections. Only runtime's App
 # object and Cosmic's unrelated shaping caches are replaced by these adapters.
 (d/'lib.rs').write_text('''use itertools::Itertools as _;
use std::sync::{RwLock, OnceLock};
struct HeldDb(fontdb::Database);
impl HeldDb {fn db(&self)->&fontdb::Database{&self.0}}
struct PartialState{font_system:HeldDb}
struct StandInLock(RwLock<PartialState>);
impl StandInLock{
    fn read(&self)->std::sync::RwLockReadGuard<'_,PartialState>{self.0.read().unwrap()}
}
pub(crate) struct CosmicTextSystem(StandInLock);
impl CosmicTextSystem {
    fn new(db:fontdb::Database)->Self{Self(StandInLock(RwLock::new(PartialState{font_system:HeldDb(db)})))}
'''+query+'''
}
use smol_str::SmolStr;
'''+shared+'''
pub(crate) struct TextSystem{platform_text_system:CosmicTextSystem}
impl TextSystem{
    fn new(db:fontdb::Database)->Self{Self{platform_text_system:CosmicTextSystem::new(db)}}
'''+names+'''
    pub(crate) fn component_names(&self,slot:&OnceLock<Vec<String>>)->bool{
        let names=slot.get_or_init(|| self.all_font_names());
        names.is_empty()
    }
    fn text_system(&self)->&Self{self}
    pub(crate) fn desktop_names(&self)->Vec<SharedString>{
        let cx=self;
'''+x+'''
        installed
    }
}
#[cfg(test)] mod meter;
#[cfg(test)] mod exercise;
''')
 for f in ('meter.rs','exercise.rs'):(d/f).write_bytes((pack/f).read_bytes())
