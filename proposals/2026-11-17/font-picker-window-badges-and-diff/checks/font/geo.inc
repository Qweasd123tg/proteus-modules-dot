// Stand-ins for GPUI geometry and window observations only. Numeric operations are f32.
#![allow(dead_code)]
type Pixels=f32;
const fn px(v:f32)->f32{v}
trait Half{fn half(self)->Self;} impl Half for f32{fn half(self)->Self{self/2.}}
#[derive(Clone,Copy,Debug,Default)]struct Size<T>{width:T,height:T}
#[derive(Clone,Copy,Debug,Default)]struct Point<T>{x:T,y:T} fn point<T>(x:T,y:T)->Point<T>{Point{x,y}}
#[derive(Clone,Copy,Debug,Default)]struct Edges<T>{left:T,right:T,top:T,bottom:T}
#[derive(Clone,Copy,Debug,Default)]struct Bounds<T>{origin:Point<T>,size:Size<T>}
impl Bounds<f32>{fn new(origin:Point<f32>,size:Size<f32>)->Self{Self{origin,size}}fn left(self)->f32{self.origin.x}fn right(self)->f32{self.origin.x+self.size.width}fn top(self)->f32{self.origin.y}fn bottom(self)->f32{self.origin.y+self.size.height}fn center(self)->Point<f32>{point(self.left()+self.size.width/2.,self.top()+self.size.height/2.)}}
#[derive(Clone,Copy,Debug,PartialEq)]enum Align{Start,Center,End}
#[derive(Clone,Copy,Debug,PartialEq)]enum Placement{Top,Bottom,Left,Right}
#[derive(Clone,Copy,Default)]struct Tiling{left:bool,right:bool,top:bool,bottom:bool}
#[derive(Clone,Copy)]enum Decorations{Server,Client{tiling:Tiling}}
struct Window{vh:f32,zoom:f32,inset:f32,dec:Decorations}
impl Window{fn client_inset(&self)->Option<f32>{Some(self.inset)}fn window_decorations(&self)->Decorations{self.dec}fn rem_size(&self)->f32{16.*self.zoom}fn viewport_size(&self)->Size<f32>{Size{width:920.,height:self.vh}}}
struct Positioner;
mod prefs{pub(super) struct Rem(f32);pub(super) fn scaled(v:f32)->Rem{Rem(v/16.)}impl Rem{pub(super) fn to_pixels(self,rem:f32)->f32{self.0*rem}}}
