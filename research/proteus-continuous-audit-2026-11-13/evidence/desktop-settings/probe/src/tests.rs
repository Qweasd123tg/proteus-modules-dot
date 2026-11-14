use super::*;
use settings::draft::FieldPath;
use serde_json::json;
fn snapshot(a:i64,b:i64)->ConfigBuilderSnapshot {
 ConfigBuilderSnapshot {writable:true, permission_mode:"normal".into(),
 module_config: [("tool".into(),[("files".into(),json!({"a":a,"b":b}))].into())].into(),
 ..Default::default()}
}
fn setup()->(SettingsView,Context<SettingsView>) {
 let mut v=SettingsView::default();v.accept(snapshot(1,1));
 (v,Context(PhantomData))
}
fn change_a(v:&mut SettingsView,cx:&mut Context<SettingsView>,n:i64){v.update_draft(cx,|d|d.set_value(&FieldPath::new("tool","files","a"),Some(json!(n))));}
fn acknowledge_save(v:&mut SettingsView,snapshot:ConfigBuilderSnapshot){
 let revision=v.edit_revision;v.saving=true;v.saving=false;v.accept_save(snapshot,revision);
}
#[test] fn save_is_allowed_while_reload_is_pending() {
 let (mut v,mut cx)=setup();v.reloading=true;change_a(&mut v,&mut cx,2);
 assert!(v.can_save());
 eprintln!("reloading={}, dirty={}, can_save={}",v.reloading,v.dirty(),v.can_save());
}
#[test] fn delayed_reload_after_save_reverts_ack_and_next_same_slot_edit_reverts_server_value() {
 let (mut v,mut cx)=setup();let stale_get=snapshot(1,1);v.reloading=true;
 change_a(&mut v,&mut cx,2);assert!(v.can_save());
 let first=v.draft.changes(&v.baseline); assert_eq!(first.module_config["tool"]["files"]["a"],2);
 acknowledge_save(&mut v,snapshot(2,1)); assert!(!v.dirty());
 v.complete_reload(Ok(stale_get),&mut cx);
 assert_eq!(v.draft.config["tool"]["files"]["a"],1);assert!(!v.dirty());
 v.update_draft(&mut cx,|d|d.set_value(&FieldPath::new("tool","files","b"),Some(json!(2))));
 let second=v.draft.changes(&v.baseline);
 assert_eq!(second.module_config["tool"]["files"],json!({"a":1,"b":2}));
 eprintln!("first successful Save={}; delayed GET sets a=1 and dirty=false; next edit b=2 emits {}",serde_json::to_string(&first.module_config).unwrap(),serde_json::to_string(&second.module_config).unwrap());
}
#[test] fn control_reload_before_save_ack_preserves_edit_then_ack() {
 let (mut v,mut cx)=setup();v.reloading=true;change_a(&mut v,&mut cx,2);
 v.complete_reload(Ok(snapshot(1,1)),&mut cx);assert!(v.dirty());
 assert_eq!(v.draft.config["tool"]["files"]["a"],2);
 acknowledge_save(&mut v,snapshot(2,1));assert!(!v.dirty());
 assert_eq!(v.draft.config["tool"]["files"]["a"],2);
}
#[test] fn control_dirty_newer_edit_protects_from_old_reload() {
 let (mut v,mut cx)=setup();v.reloading=true;change_a(&mut v,&mut cx,2);
 acknowledge_save(&mut v,snapshot(2,1));
 v.update_draft(&mut cx,|d|d.set_value(&FieldPath::new("tool","files","b"),Some(json!(2))));
 v.complete_reload(Ok(snapshot(1,1)),&mut cx);
 assert_eq!(v.draft.config["tool"]["files"],json!({"a":2,"b":2}));assert!(v.dirty());
}
