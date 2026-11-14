use proteus_tabs::{TabLayout, Edge};
fn roll(seed: &mut u64) -> usize {*seed ^= *seed << 13; *seed ^= *seed >> 7; *seed ^= *seed << 17; *seed as usize}
fn main() {
for start in 1..=4000 {
 let mut r=start; let mut layout=TabLayout::default(); let mut trace=vec![];
 for step in 0..500 {
  let n=roll(&mut r); let kind=n%12; let id=format!("files:{}", roll(&mut r)%12);
  let panes=layout.panes().iter().map(|p| p.id).collect::<Vec<_>>(); let pane=panes[roll(&mut r)%panes.len()];
  let ids=layout.panes().iter().flat_map(|p|p.tabs.clone()).collect::<Vec<_>>();
  let tab=if ids.is_empty(){id.clone()}else{ids[roll(&mut r)%ids.len()].clone()};
  let edge=[Edge::Left,Edge::Right,Edge::Top,Edge::Bottom][roll(&mut r)%4];
  let op=match kind {
   0=>{layout.open(&id, |_|false);format!("open {id}")},
   1=>{layout.open_preview(&id, |_|false);format!("preview {id}")},
   2=>{layout.close(&tab);format!("close {tab}")},
   3=>{layout.split(&tab,pane,edge);format!("split {tab} {pane:?} {edge:?}")},
   4=>{layout.close_pane(pane);format!("close pane {pane:?}")},
   5=>{layout.lock_pane(pane,true,1200.,900.,5.);format!("lock {pane:?}")},
   6=>{layout.lock_pane(pane,false,1200.,900.,5.);format!("unlock {pane:?}")},
   7=>{layout.set_pinned(&tab,true);format!("pin {tab}")},
   8=>{layout.set_pinned(&tab,false);format!("unpin {tab}")},
   9=>{layout.move_tab(&tab,pane,None);format!("move {tab} {pane:?}")},
   10=>{layout.focus(pane);format!("focus {pane:?}")},
   _=>{if let Some(c)=layout.take_closed(|_|true) {layout.restore_closed(&c)};"reopen".into()},
  };
  trace.push(op);
  if let Err(e)=layout.validate(){println!("seed {start}, step {step}: {e}\n{}\n{layout:#?}",trace.join("\n")); std::process::exit(1)};
 }
}
println!("2,000,000 bounded UI-model operations preserved layout validation");
}
