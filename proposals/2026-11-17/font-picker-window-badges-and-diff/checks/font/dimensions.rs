// Mirrors the reduced Render tree. Geometry is solved by the actual Taffy 0.15.0 flex/block engine.
use taffy::{prelude::{TaffyTree,Style,Display,FlexDirection,length,percent,auto,AvailableSpace,Position,Rect},geometry::{Point as TPoint,Size as TSize},style::Overflow};
fn base()->Style{Style{display:Display::Block,..Default::default()}}
fn flex(dir:FlexDirection)->Style{Style{display:Display::Flex,flex_direction:dir,..base()}}
fn geom(window:&Window, count:usize)->(f32,f32,f32,f32){
 let zoom=window.zoom; let mut t:TaffyTree<()>=TaffyTree::new();
 let h=|v:f32|TSize{width:auto(),height:length(v)};
 let w=|v:f32|TSize{width:length(v),height:auto()};
 let full=TSize{width:percent(1.),height:auto()};
 let search=t.new_leaf(Style{size:h(24.*zoom),..flex(FlexDirection::Row)}).unwrap();
 let header=t.new_with_children(Style{size:full,..flex(FlexDirection::Row)},&[search]).unwrap();
 let rows=t.new_leaf(Style{size:TSize{width:percent(1.),height:length(ROW*zoom*count.min(VISIBLE) as f32)},overflow:TPoint{x:Overflow::Visible,y:Overflow::Scroll},..base()}).unwrap();
 let max_size=TSize{width:auto(),height:match font_limit(window){Some(v)=>length(v),None=>auto()}};
 let picker=t.new_with_children(Style{size:full,max_size,gap:TSize{width:length(4.*zoom),height:length(4.*zoom)},..flex(FlexDirection::Column)},&[header,rows]).unwrap();
 let all=|v:f32|Rect{left:length(v),right:length(v),top:length(v),bottom:length(v)};
 let body=t.new_with_children(Style{size:w((300.*zoom).min(920.-16.*zoom)),padding:all(6.*zoom),..flex(FlexDirection::Column)},&[picker]).unwrap();
 let surface=t.new_with_children(Style{border:all(1.),overflow:TPoint{x:Overflow::Hidden,y:Overflow::Hidden},..base()},&[body]).unwrap();
 let position=t.new_with_children(Style{position:Position::Absolute,..flex(FlexDirection::Row)},&[surface]).unwrap();
 let trigger=t.new_with_children(Style{size:TSize{width:length(160.*zoom),height:length(24.*zoom)},..base()},&[position]).unwrap();
 let root=t.new_with_children(Style{size:TSize{width:length(920.),height:length(window.vh)},..base()},&[trigger]).unwrap();
 t.compute_layout(root,TSize{width:AvailableSpace::Definite(920.),height:AvailableSpace::Definite(window.vh)}).unwrap();
 let local_row_y=t.layout(rows).unwrap().location.y+t.layout(picker).unwrap().location.y+t.layout(body).unwrap().location.y;
 (t.layout(surface).unwrap().size.height,t.layout(header).unwrap().size.height,local_row_y,t.layout(rows).unwrap().size.height)
}
fn main() {
 let mut n=0;let mut outside=0;let mut partial=0;let mut bad_header=0; let mut changed_without_need=0;
 for scale in [75,80,90,100,110,125,150,175,200]{let zoom=scale as f32/100.;
 for vh in [240.,320.,360.,440.,480.,600.,820.] {for mask in 0..5{for count in [1usize,2,7,8,9,40,125]{
 let dec=if mask==0{Decorations::Server}else{Decorations::Client{tiling:Tiling{top:(mask-1)&1!=0,bottom:(mask-1)&2!=0,..Tiling::default()}}};
 let window=Window{vh,zoom,inset:20.,dec};let (height,header,local,rows)=geom(&window,count);
 let f=frame_insets(dec,window.inset);
 let margins=Edges{left:8.+f.left,right:8.+f.right,top:8.+f.top,bottom:8.+f.bottom};
 let area=window.viewport_size();let trigger=Bounds::new(point(100.,vh*0.45),Size{width:100.,height:24.*zoom});
 let popup=Size{width:300.*zoom,height};
 let side=resolve_placement(trigger,popup,area,margins,Some(Placement::Bottom));
 let actual=clamp(Bounds::new(side_origin(trigger,popup,side,Align::End,4.),popup),area,margins);
 let row_h=(28.*zoom).round(); // measured row height at this fixture's device pixel ratio = 1.
 let max_scroll=(row_h*count as f32-rows).max(0.);
 let top=actual.top()+local+(count-1) as f32*row_h-max_scroll;
 let bottom=top+row_h; n+=1;
 if top>=vh{outside+=1;}
 if bottom>vh-margins.bottom+1.{partial+=1;}
 if (header-24.*zoom).abs()>1.{bad_header+=1;}
 // When the regular control fits, actual geometry must not be smaller than its intrinsic dimensions (rounding by Taffy).
 let natural=2.+(24.+4.+12.+28.*count.min(8) as f32)*zoom;
 if natural<=vh-margins.top-margins.bottom-1.&&(height-natural).abs()>1.{changed_without_need+=1;}
 if scale==200&&vh==440.&&mask==0&&(count==8||count==40){println!("case scale={} height={} count={} popup={} header={} rows={} scroll={} last={}..{} usable=8..432",scale,vh,count,height,header,rows,max_scroll,top,bottom);}
 }}}}
 println!("cases={n}; entire_last_row_below_window={outside}; last_row_not_fully_inside_margin={partial}; header_regressions={bad_header}; unnecessary_shrink={changed_without_need}");
 assert_eq!((outside,partial,bad_header,changed_without_need),(0,0,0,0));
}
