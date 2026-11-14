use proteus_tabs::{TabLayout,Edge};
fn main(){
 let mut l=TabLayout::default();
 for id in ["files:a","files:b","files:c","files:d"] {l.open(id, |_|false);}
 l.split("files:b",l.pane_of("files:a").unwrap(),Edge::Bottom);
 l.split("files:c",l.pane_of("files:b").unwrap(),Edge::Right);
 l.split("files:d",l.pane_of("files:b").unwrap(),Edge::Bottom);
 l.lock_pane(l.pane_of("files:b").unwrap(),true,1200.,900.,5.);
 l.close("files:d");
 println!("before: {:?}\n{}",l.validate(),serde_json::to_string_pretty(&l).unwrap());
 assert_eq!(l.validate(),Ok(()));
 l.close("files:c");
 println!("after: {:?}\n{}",l.validate(),serde_json::to_string_pretty(&l).unwrap());
 assert_eq!(l.validate(),Ok(()));
}
