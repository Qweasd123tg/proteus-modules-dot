}
use subject::*;
fn setup(n:usize,k:usize,missing:Option<usize>)->(Pane,Bounds<i32>){
 let p=Pane{id:0,tabs:(0..n).map(|i|format!("document:/work/project/folder/file-{i}.rs")).collect(),pinned:k};
 STATE.with_borrow_mut(|s|{s.target=Target::Home;s.bounds.clear();for (i,id)in p.tabs.iter().enumerate(){
 if missing==Some(i){continue;}let x=(i as i32)*20;s.bounds.insert(id.clone(),Bounds{left:x,right:x+18,top:0,bottom:10});}});
 let b=Bounds{left:-20,right:n as i32*20+20,top:0,bottom:10};(p,b)
}
fn expected(p:&Pane,drag:&str,pinned:bool,missing:Option<usize>,x:i32)->(usize,Option<String>){
 let mut earlier=0;let mut k=0;let mut ids=vec![];
 for(i,t)in p.tabs.iter().enumerate(){if t==drag{continue}if i<p.pinned{k+=1}if Some(i)!=missing && ((i as i32)*20+9)<x{earlier+=1}ids.push(t);}
 let at=if pinned{earlier.min(k)}else{earlier.max(k)};
 (at,ids.get(at).map(|id|id.to_string()))
}
fn correctness()->usize{
 let mut cases=0;
 for n in 0..=7 {for k in 0..=n {for missing in [None,Some(n/2)]{let (p,strip)=setup(n,k,missing);
 for d in 0..=n {let id=p.tabs.get(d).map(|s|s.as_str()).unwrap_or("doc:external");
 for pinned in [false,true] {if d<n && pinned!=(d<k){continue}
 let mut w=Window::default();for x in -10..=(n as i32*20+10) {
 let (ix,before)=expected(&p,id,pinned,missing,x);hover(&p,id,pinned,strip,Point{x,y:6},&mut w);
 assert_eq!(STATE.with_borrow(|s|s.target),Target::At(0,ix));assert_eq!(drop_before(&p,id),Some(before));
 cases+=1;
 }hover(&p,id,pinned,strip,Point{x:-1000,y:0},&mut w);assert_eq!(drop_before(&p,id),None);
 }}}}}cases
}
fn main(){
 let correctness_count=correctness();
 println!("correct_ordering={correctness_count}");
 let mut meets=true;
 for n in [1usize,8,24,64,128]{
 let (p,bounds)=setup(n,n/3,None);let d=n/2;let drag=p.tabs[d].as_str();
 let mut w=Window::default();
 let (_,hc,hb)=measured(||{for j in 0..120{
 let x=(j as i32*13)%(bounds.right+1);hover(&p,drag,d<p.pinned,bounds,Point{x,y:5},&mut w);
 std::hint::black_box(STATE.with_borrow(|s|s.target));}});
 // One explicit middle target and one append target; both states are prepared outside the measurements.
 STATE.with_borrow_mut(|s|s.target=Target::At(p.id,n/3));
 let (drop_id,dc,db)=measured(||drop_before(&p,drag));
 STATE.with_borrow_mut(|s|s.target=Target::At(p.id,n-1));
 let (end,ec,eb)=measured(||drop_before(&p,drag));
 assert_eq!(end,Some(None));
 let found=drop_id.unwrap().is_some();
 println!("tabs {n:3} | 120 hovers {hc:6} calls {hb:8} requested bytes | drop_before {dc:3} calls {db:6} bytes found={found} | append {ec:3} calls {eb:6} bytes");
 meets &= hc==0 && dc==usize::from(found) && ec==0;
 }
 assert!(meets,"materializing other tab IDs on hover or unselected drop");
}
