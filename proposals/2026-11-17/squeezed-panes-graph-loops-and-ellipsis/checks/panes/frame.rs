// Reproduction, not a product patch. Rectangle inputs use logical pixels, excluding seams.
#![allow(dead_code)]
mod proof {
const EPSILON:f32=1e-4;
#[derive(Clone, Copy, Debug, PartialEq)]
enum Size { Weight(f32), Fixed(f32) }
impl Size { @@SIZE@@ }
#[derive(Clone, Copy, Debug, PartialEq)] enum Axis { Row, Column }
enum Node { Pane(()), Split(Split) }
struct Split { children: Vec<Child>, axis: Axis }
pub(super) struct Child { size: Size, node: Node }
struct TabLayout { root: Node }
impl Node {
    // This probe only addresses an existing, flat root split.
    fn split_at_mut(&mut self,path:&[usize])->Option<&mut Split> {
        assert!(path.is_empty());
        if let Node::Split(s)=self {Some(s)} else {None}
    }
    @@ROOT@@
}
@@FREE@@
impl TabLayout { @@GEOMETRY@@ }
fn sample(axis:Axis, sizes:&[Size], divider:usize, requested:f32,total:f32,min:f32)->(Vec<f32>,Vec<f32>,Vec<Size>) {
    let mut l=TabLayout{root:Node::Split(Split{axis,children:sizes.iter().map(|s|Child{size:*s,node:Node::Pane(())}).collect()})};
    let before=extents(&l.root.split_at_mut(&[]).unwrap().children,total);
    l.resize(&[],divider,requested,total,min);
    let split=l.root.split_at_mut(&[]).unwrap();
    (before,extents(&split.children,total),split.children.iter().map(|c|c.size).collect())
}
pub fn run(){
    let candidate=std::env::args().any(|s|s=="candidate");
    use Size::{Fixed as FF,Weight as WW};
    let (b,disp,sizes)=sample(Axis::Row,&[FF(799.),FF(399.5),WW(1.)],0,400.,998.,240.);
    if candidate {assert_eq!(disp,vec![400.,598.,0.]);assert_eq!(sizes,vec![FF(400.),FF(598.),WW(1.)]);}
    else {assert_eq!(disp,b);}
    println!("two fixed + one collapsed: {b:?} => {disp:?}, saved {sizes:?}");
    for (width,target) in [(400.,270.),(700.,480.),(700.,465.)] {
        let original=[FF(799.),FF(399.5),WW(1.)];
        let (prior,shown,saved)=sample(Axis::Row,&original,0,target,width,240.);
        assert_eq!(prior,shown);assert_eq!(&saved, &original);
    }
    println!("infeasible, reversed and overshooting movements leave the saved widths alone");
    let mut n=0;
    let mut outside=0;
    for count in 3..=10usize {
      for index in 0..count-1 {
        for axis in [Axis::Column,Axis::Row] {
          let min=if axis==Axis::Row{240.}else{160.};
          for ratio in [1.0,1.25,1.5,2.0,4.0] {
            let mut state=(0..count).map(|i|WW((i+1) as f32)).collect::<Vec<_>>();
            state[index]=FF(1024.*ratio);state[index+1]=FF(1024.);
            let wide=state.clone();let total=1000.;
            let (init,_,_)=sample(axis,&state,index,0.,total,min);
            let at=init[index];
            let (_,_,stationary)=sample(axis,&state,index,at,total,min);
            assert_eq!(state,stationary);
            for target in [500.,450.,400.,480.,600.,500.] {
                let (old,vis,next)=sample(axis,&state,index,target,total,min);
                if candidate {
                    assert!((vis[index]-target).abs()<0.001 && (vis[index+1]-(total-target)).abs()<0.001);
                    for (i,v) in next.iter().enumerate() {
                      if i!=index && i!=index+1 {assert_eq!(*v,wide[i]);assert_eq!(vis[i],0.);}
                    }
                    // No rewrite of historical preferences on a genuine no-op.
                    if old[index]!=target{
                       assert_eq!(next[index],FF(target));assert_eq!(next[index+1],FF(total-target));
                       let (expanded,_,_)=sample(axis,&next,index,target,total+2000.,min);
                       assert!((expanded[index]-target).abs()<0.001);
                    }
                } else {assert_eq!(state,next);assert_eq!(vis,old);}
                state=next;n+=1;
            }
            if count>=4 {
              let mut more=wide.clone();more[if index>=1 {0}else{count-1}]=FF(250.);
              let (_,_,still)=sample(axis,&more,index,500.,total,min);assert_eq!(still,more);outside+=1;
            }
          }
        }
      }
    }
    println!("{n} consecutive moves with exactly two locked siblings; {outside} controls with an additional fixed sibling.");

    use Size::{Fixed as F,Weight as W};
    for (count, sizes, ix, requested, total, expected) in [
        (3,vec![W(1.),W(1.),F(1050.)],1,600.,998.,vec![0.,0.,998.]),
        (3,vec![F(1050.),W(1.),W(1.)],0,400.,998.,vec![998.,0.,0.]),
        (2,vec![W(1.),F(1050.)],0,600.,998.,vec![600.,398.]),
        (3,vec![W(1.),W(1.),F(1050.)],1,600.,1200.,vec![75.,525.,600.]),
    ]{
        let (before,after,_)=sample(Axis::Row,&sizes,ix,requested,total,240.);
        assert_eq!(after, expected);
        println!("{count} panes; {sizes:?}; available {total}; boundary {ix} -> {requested}: {before:?} => {after:?}");
    }
    let mut no_op=0; let mut controls=0;
    for axis in [Axis::Row, Axis::Column] {
      let min=if axis==Axis::Row {240.} else {160.};
      for n in 3..=10 {
        for wide in [1024.,1280.,1600.] {
          for excess in [0.,64.,512.] {
            for direction in [false,true]{
              for weights in [1.,2.,3.]{
                let mut sizes=vec![W(1.);n];for (i,s) in sizes.iter_mut().enumerate(){*s=W(if i%2==0{weights}else{1.})}
                let (fixed,ix,target)=if direction{(0,0,wide*0.4)}else{(n-1,n-2,wide*0.6)};
                sizes[fixed]=F(wide+excess);
                let (b,a,ss)=sample(axis,&sizes,ix,target,wide,min);
                assert_eq!(b,a);assert_eq!(ss,sizes);no_op+=1;
              }
            }
          }
        }
      }
      // Without a third zero-weighted-width sibling, the same handle is effective.
      for wide in [1024.,1280.,1600.] {for side in [false,true]{for excess in [0.,64.,512.] {
        let s=if side{vec![F(wide+excess),W(1.)]}else{vec![W(1.),F(wide+excess)]};
        let (b,a,_)=sample(axis,&s,0,wide*0.5,wide,min);assert_ne!(b,a);assert_eq!(a[0],wide*0.5);controls+=1;
      }}}
    }
    println!("{no_op} saturated endpoint-divider drags (3-10 panes) are no-ops; {controls} matching two-pane controls move.");
}}
fn main(){proof::run()}
