use proteus_tabs::{TabLayout,PaneId,Edge};
fn apply(l:&mut TabLayout,s:&str){
 let a=s.split_whitespace().collect::<Vec<_>>();
 let p=|at:usize|PaneId(a[at].trim_start_matches("PaneId(").trim_end_matches(')').parse().unwrap());
 match a[0]{
 "open"=>l.open(a[1], |_|false), "preview"=>l.open_preview(a[1], |_|false),
 "split"=>l.split(a[1],p(2),match a[3]{"Left"=>Edge::Left,"Right"=>Edge::Right,"Top"=>Edge::Top,_=>Edge::Bottom}),
 "close" if a[1]=="pane"=>l.close_pane(p(2)), "close"=>l.close(a[1]),
 "lock"=>l.lock_pane(p(1),true,1200.,900.,5.),"unlock"=>l.lock_pane(p(1),false,1200.,900.,5.),
 "pin"=>l.set_pinned(a[1],true),"unpin"=>l.set_pinned(a[1],false),
 "move"=>l.move_tab(a[1],p(2),None),"focus"=>l.focus(p(1)),
 "reopen"=>if let Some(c)=l.take_closed(|_|true){l.restore_closed(&c)},_=>panic!("{s}"),
 }
}
fn run(seq:&[String])->(bool,TabLayout,usize){let mut l=TabLayout::default();for(i,s)in seq.iter().enumerate(){apply(&mut l,s);if let Err(e)=l.validate(){return(e=="an empty pane is next to chats or documents",l,i+1)}}(false,l,seq.len())}
fn main(){
 let raw=std::fs::read_to_string("audit-round5/model-fuzz.log").unwrap();
 let mut seq=raw.lines().skip_while(|s|!s.starts_with("seed ")).skip(1).take_while(|s|*s!="TabLayout {").map(str::to_string).collect::<Vec<_>>();
 let mut n=2;
 loop{let chunk=seq.len().div_ceil(n);let mut change=false;
 for at in (0..seq.len()).step_by(chunk){let mut cand=seq.clone();cand.drain(at..(at+chunk).min(seq.len()));let (bad,_,len)=run(&cand);if bad{cand.truncate(len);seq=cand;change=true;break}}
 if change{n=2;}else if n>=seq.len(){break}else{n=(n*2).min(seq.len())}
 }
 println!("{} steps:\n{}\n{:#?}",seq.len(),seq.join("\n"),run(&seq).1);
 std::fs::write("audit-round5/minimized-ops.txt",seq.join("\n")).unwrap();
}
