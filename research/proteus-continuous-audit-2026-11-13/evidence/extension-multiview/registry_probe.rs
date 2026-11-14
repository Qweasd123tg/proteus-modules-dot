
use std::any::{Any,TypeId};
use std::collections::HashMap;
use std::rc::{Rc,Weak};
struct Entity<T> { id:u64, value:Rc<T> }
impl<T> Clone for Entity<T> {fn clone(&self)->Self{Self{id:self.id,value:self.value.clone()}}}
impl<T> Entity<T> {
 fn new(id:u64,value:T)->Self{Self{id,value:Rc::new(value)}}
 fn entity_id(&self)->u64{self.id}
 fn downgrade(&self)->WeakEntity<T>{WeakEntity{id:self.id,value:Rc::downgrade(&self.value)}}
 fn read(&self,_:&App)->&T{&self.value}
}
struct WeakEntity<T> {id:u64,value:Weak<T>}
impl<T> WeakEntity<T> {fn upgrade(&self)->Option<Entity<T>>{Some(Entity{id:self.id,value:self.value.upgrade()?})}}
struct Runtime {extension:&'static str}
impl Runtime {fn extension_id(&self)->&str{self.extension}}
#[derive(Default)]struct Runtimes(HashMap<(u64,&'static str),WeakEntity<Runtime>>);
#[derive(Default)]struct ViewRuntimes(HashMap<u64,WeakEntity<Runtime>>);
#[derive(Default)]struct App {globals:HashMap<TypeId,Box<dyn Any>>,retained:HashMap<(u64,&'static str),Entity<Runtime>>}
impl App{
 fn default_global<T:Default+'static>(&mut self)->&mut T{self.globals.entry(TypeId::of::<T>()).or_insert_with(||Box::new(T::default())).downcast_mut().unwrap()}
 fn try_global<T:'static>(&self)->Option<&T>{self.globals.get(&TypeId::of::<T>())?.downcast_ref()}
}
struct Host {identity:u64,extension:&'static str}
impl Host{
 fn identity(&self)->u64{self.identity}
 fn extension(&self)->&'static str{self.extension}
 fn retain_process(&self,runtime:Entity<Runtime>,cx:&mut App){cx.retained.insert((self.identity,self.extension),runtime);}
}

fn rehost_runtime(runtime: &Entity<Runtime>, host: &Host, cx: &mut App) {
    cx.default_global::<Runtimes>()
        .0
        .insert((host.identity(), host.extension()), runtime.downgrade());
    host.retain_process(runtime.clone().into(), cx);
}
mod runtime { use super::*;
mod invalidation { use super::*; use std::{collections::HashSet,hash::Hash};
fn targets<'a, I: Eq + Hash, T>(
    extension: &str,
    entries: impl IntoIterator<Item = (&'a str, I, T)>,
) -> Vec<T> {
    let mut seen = HashSet::new();
    entries
        .into_iter()
        .filter_map(|(owner, identity, runtime)| {
            (owner == extension && seen.insert(identity)).then_some(runtime)
        })
        .collect()
}
pub(super) fn runtimes(extension: &str, cx: &App) -> Vec<Entity<Runtime>> {
    let mut runtimes = cx
        .try_global::<super::super::Runtimes>()
        .map(|runtimes| {
            targets(
                extension,
                runtimes.0.iter().filter_map(|((_, owner), runtime)| {
                    let runtime = runtime.upgrade()?;
                    Some((*owner, runtime.entity_id(), runtime))
                }),
            )
        })
        .unwrap_or_default();
    if let Some(owned) = cx.try_global::<super::super::ViewRuntimes>() {
        runtimes.extend(
            owned
                .0
                .values()
                .filter_map(WeakEntity::upgrade)
                .filter(|runtime| runtime.read(cx).extension_id() == extension),
        );
    }
    let mut seen = HashSet::new();
    runtimes.retain(|runtime| seen.insert(runtime.entity_id()));
    runtimes
}
}
pub(super) fn targets_for_test(extension:&str,cx:&App)->Vec<Entity<Runtime>>{invalidation::runtimes(extension,cx)}
}

fn scenario()->(App,Entity<Runtime>,Entity<Runtime>){
 let mut app=App::default();
 let a=Entity::new(101,Runtime{extension:"files"});
 let b=Entity::new(202,Runtime{extension:"files"});
 let host_a=Host{identity:1,extension:"files"};
 let host_b=Host{identity:2,extension:"files"};
 rehost_runtime(&a,&host_a,&mut app);
 rehost_runtime(&b,&host_b,&mut app);
 assert_eq!(runtime::targets_for_test("files",&app).len(),2);
 // A document moves into the window whose existing panel still owns B.
 rehost_runtime(&a,&host_b,&mut app);
 (app,a,b)
}
#[test]fn observed_live_displaced_runtime_disappears_from_targets(){
 let (app,a,existing_panel_runtime)=scenario();
 let ids:Vec<_>=runtime::targets_for_test("files",&app).iter().map(Entity::entity_id).collect();
 println!("targets={ids:?}; alive_existing_panel_runtime={}",existing_panel_runtime.entity_id());
 assert_eq!(ids,vec![a.entity_id()]);
 assert!(existing_panel_runtime.downgrade().upgrade().is_some());
}
#[test]#[ignore]fn required_broadcast_includes_still_live_existing_panel_runtime(){
 let (app,_,existing_panel_runtime)=scenario();
 let ids:Vec<_>=runtime::targets_for_test("files",&app).iter().map(Entity::entity_id).collect();
 assert!(ids.contains(&existing_panel_runtime.entity_id()),"existing view remains live, so its runtime must remain an invalidation/retarget target: {ids:?}");
}
#[test]fn control_alias_dedup_keeps_other_extension_out(){
 let(mut app,a,b)=scenario();
 // Another surviving alias of B keeps it discoverable.
 rehost_runtime(&b,&Host{identity:3,extension:"files"},&mut app);
 let other=Entity::new(303,Runtime{extension:"other"});
 rehost_runtime(&other,&Host{identity:4,extension:"other"},&mut app);
 let mut ids:Vec<_>=runtime::targets_for_test("files",&app).iter().map(Entity::entity_id).collect();ids.sort();
 assert_eq!(ids,vec![a.entity_id(),b.entity_id()]);
}
