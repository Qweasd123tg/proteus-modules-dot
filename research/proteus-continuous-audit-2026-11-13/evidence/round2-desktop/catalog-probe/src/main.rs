use std::{fs, path::{Path,PathBuf},process::Command};
use std::os::unix::fs::PermissionsExt;
#[path="../../../src/packages.rs"] mod packages;
mod catalog;
fn git(root:&Path,args:&[&str])->String{ let o=Command::new("git").args(args).current_dir(root).output().unwrap(); assert!(o.status.success(),"{:?}",o);String::from_utf8(o.stdout).unwrap().trim().to_string() }
fn commit(repo:&Path,version:&str)->String{
 let index=serde_json::json!({"format":1,"title":"Fixture","categories":[{"id":"skills","title":"Skills"}],"entries":[{"id":"demo","kind":"skill","title":"Demo","description":"test","category":"skills","version":version,"path":"demo"}]});
 fs::write(repo.join("proteus-catalog.json"),index.to_string()).unwrap();
 fs::write(repo.join("demo/SKILL.md"),format!("# {version} contents")).unwrap();
 git(repo,&["add","."]);git(repo,&["commit","-m",version]);git(repo,&["rev-parse","HEAD"])
}
fn main(){
 let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!("fixture-{}", uuid::Uuid::new_v4()));
 fs::create_dir(&root).unwrap(); println!("fixture: {}", root.display());
 let repo=root.join("origin"); fs::create_dir_all(repo.join("demo")).unwrap();
 git(&repo,&["init","--template=","--initial-branch=main"]);git(&repo,&["config","user.name","Fixture"]);git(&repo,&["config","user.email","fixture@example.invalid"]);git(&repo,&["config","commit.gpgsign","false"]);
 let a=commit(&repo,"A");let source=catalog::Source{url:repo.to_string_lossy().into(),branch:Some("main".into())};let cache=root.join("cache");
 let first=catalog::git::refresh(&cache,&source).unwrap();assert_eq!(first.revision.as_deref(),Some(a.as_str()));
 let b=commit(&repo,"B");let state=cache.join(format!(".state-{}.json",source.key()));
 fs::set_permissions(&state,fs::Permissions::from_mode(0o400)).unwrap();
 let error=catalog::git::refresh(&cache,&source).err().expect("state write must fail");
 println!("refresh B failure: {error:#}");
 fs::set_permissions(&state,fs::Permissions::from_mode(0o600)).unwrap();
 let mixed=catalog::git::cached(&cache,&source).unwrap();
 println!("cached declared version={} revision={} (A={}, B={})", mixed.entries[0].version,mixed.revision.as_ref().unwrap(),a,b);
 assert_eq!(mixed.entries[0].version,"B");assert_eq!(mixed.revision.as_deref(),Some(a.as_str()));
 let paths=[mixed.entries[0].path.clone()];
 let bytes=catalog::git::with_files(&cache,&source,mixed.revision.as_deref(),&paths,|| Ok(fs::read_to_string(mixed.root.join("demo/SKILL.md"))?)).unwrap();
 println!("Allowed package content after failed refresh: {bytes}");
 assert_eq!(bytes,"# A contents");
 println!("CONFIRMED: catalog advertises B while revision gate admits and reads A.");
}
