extern crate proteus_diff as d;
use d::{FileInfo,parse,Kind,Pair};
fn main(){
 let statuses=["added","untracked","modified","renamed","conflict","","???","deleted"];
 let variants:[(&str,&str);5]=[
    ("",""),
    ("diff --git a/q b/q\nnew file mode 100644\n","q"),
    ("diff --git a/q b/q\ndeleted file mode 100644\n","q"),
    ("diff --git a/old b/q\nsimilarity index 100%\nrename from old\nrename to q\n","q"),
    ("diff --git a/q b/q\n--- a/q\n+++ b/q\n@@ -1 +1 @@\n-old\n+new\n","q")];
 let mut neutral=0;let mut errors=0;let mut stable=0;
 for (raw,matched) in variants{for status in statuses{for path in ["z","q","тест"]{for text in [None,Some("reason"),Some("理由")]{let info=FileInfo{path:path.into(),status:status.into(),message:text.map(Into::into)};
 let alone=parse(raw,&[]);let all=parse(raw,&[info]);let card=all.iter().find(|f|f.path==path).unwrap();
 if path!=matched{
   assert_eq!(&all[..alone.len()],&alone);assert!(card.patch.is_empty());assert_eq!(card.lines.len(),1);assert_eq!(card.lines[0].kind,Kind::Note);assert_eq!(card.pairs,vec![Pair::Full(0)]);assert_eq!(card.unified,vec![0]);assert_eq!((card.added,card.removed),(0,0));
   if let Some(msg)=text{assert_eq!(card.lines[0].text,msg);stable+=1;}else if status=="deleted"{assert_eq!(card.lines[0].text,"Файл удалён");stable+=1;}else{neutral+=1;if card.lines[0].text!="Текст изменений не предоставлен"{errors+=1;}}
 }else{assert_eq!(card.patch,raw);if raw.contains("@@"){assert_eq!((card.added,card.removed),(1,1));}stable+=1;}
 }}}}
 println!("{neutral} metadata-only non-deletion cases; {errors} unsubstantiated captions; {stable} unchanged controls.");
 if cfg!(baseline){assert_eq!(errors,neutral);}else{assert_eq!(errors,0);}
}
