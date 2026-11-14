use super::*;
use settings::draft::FieldPath;
use serde_json::json;
#[test] fn regression_save_cannot_overtake_unfinished_profile_reload() {
 let mut v=SettingsView::default();let mut cx=Context(PhantomData);
 let old=ConfigBuilderSnapshot{writable:true,permission_mode:"normal".into(),
   module_config:[("tool".into(),[("files".into(),json!({"a":1,"b":1}))].into())].into(),..Default::default()};
 v.accept(old.clone());v.reloading=true;
 v.update_draft(&mut cx,|d|d.set_value(&FieldPath::new("tool","files","a"),Some(json!(2))));
 assert!(!v.can_save(),"Save must not overtake the outstanding reload without a stale-response guard");
 v.complete_reload(Ok(old),&mut cx);
 assert!(v.can_save());assert_eq!(v.draft.config["tool"]["files"]["a"],2);
}
