// Native element effects are represented as a tree; production geometry and
// exact local/remote callsite expressions are compiled below.
type Pixels=f32;
#[derive(Clone,Copy)]
struct Size<T>{width:T,height:T}
#[derive(Clone,Copy,Debug,PartialEq)]
struct Hsla {rgb:[u8;3], opacity:f32}
struct Rgb{r:f32,g:f32,b:f32}
impl Hsla {
    fn opacity(self, opacity:f32)->Self{Self{opacity,..self}}
    fn to_rgb(self)->Rgb {
        let [r,g,b]=self.rgb.map(|v| f32::from(v)/255.0);
        Rgb{r,g,b}
    }
}
fn rgb(value:u32)->Hsla {
    let [_,r,g,b]=value.to_be_bytes();
    Hsla{rgb:[r,g,b],opacity:1.0}
}
#[derive(Clone,Debug,Default,PartialEq)]
struct Div {
    x:f32,y:f32,w:f32,h:f32,right:f32,
    bg:Option<Hsla>,fg:Option<Hsla>,outline:Option<Hsla>,
    bold:bool,italic:bool,underline:bool,strike:bool,border:bool,
    text:Option<String>,children:Vec<Div>,
}
struct FontWeight;
impl FontWeight {const BOLD:Self=Self;}
fn div()->Div {Div::default()}
fn px(value:f32)->f32{value}
trait IntoChild {fn add(self,parent:&mut Div);}
impl IntoChild for String {fn add(self,parent:&mut Div){parent.text=Some(self);}}
impl IntoChild for Div {fn add(self,parent:&mut Div){parent.children.push(self);}}
impl Div {
    fn absolute(self)->Self{self}
    fn size_full(self)->Self{self}
    fn top_0(self)->Self{self.top(0.0)}
    fn top(mut self,y:f32)->Self{self.y=y;self}
    fn left(mut self,x:f32)->Self{self.x=x;self}
    fn right(mut self,r:f32)->Self{self.right=r;self}
    fn h(mut self,h:f32)->Self{self.h=h;self}
    fn w(mut self,w:f32)->Self{self.w=w;self}
    fn when_some<T>(self,v:Option<T>,f:impl FnOnce(Self,T)->Self)->Self{
        if let Some(v)=v{f(self,v)}else{self}
    }
    fn when(self,b:bool,f:impl FnOnce(Self)->Self)->Self{if b{f(self)}else{self}}
    fn map(self,f:impl FnOnce(Self)->Self)->Self{f(self)}
    fn bg(mut self,c:Hsla)->Self{self.bg=Some(c);self}
    fn text_color(mut self,c:Hsla)->Self{self.fg=Some(c);self}
    fn whitespace_nowrap(self)->Self{self}
    fn font_weight(mut self,_:FontWeight)->Self{self.bold=true;self}
    fn italic(mut self)->Self{self.italic=true;self}
    fn underline(mut self)->Self{self.underline=true;self}
    fn line_through(mut self)->Self{self.strike=true;self}
    fn border_1(mut self)->Self{self.border=true;self}
    fn border_color(mut self,c:Hsla)->Self{self.outline=Some(c);self}
    fn child(mut self,c:impl IntoChild)->Self{c.add(&mut self);self}
    fn children(mut self,all:impl IntoIterator<Item=Div>)->Self{self.children.extend(all);self}
}
struct Window;
struct Focus(bool);
impl Focus {fn is_focused(&self,_:&Window)->bool{self.0}}
struct Remote<'a> {display:Option<&'a Display>,process_finished:bool, focus:Focus}
struct Source<'a>(&'a Screen);
impl Source<'_>{ fn snapshot(&self,_:Base)->Screen{self.0.clone()} }
enum State<'a>{Running(Source<'a>),Exited(Source<'a>),Absent}
impl<'a> State<'a> {
    fn terminal(&self)->Option<&Source<'a>> {
        match self { Self::Running(source)|Self::Exited(source)=>Some(source),Self::Absent=>None }
    }
}
struct Local<'a> {state:State<'a>,focus:Focus}
mod cells {
    use super::*;
    include!("cells_projection.inc.rs");
}
include!("view_projection.inc.rs");

pub(super) fn run(){
    let spawned=Display::with_engine(Grid::new(32,4),"alacritty").unwrap();
    settle_redraw(&spawned);
    let display=&spawned.display;
    let color=rgb(0xc8c8c8);
    let black=rgb(0);
    let seed=display.snapshot(BASE);
    drop(seed);
    assert!(display.feed(b"front\x1b[1;3;4;9;38;2;1;2;3;48;2;17;33;99mcolor\x1b[0m".to_vec()));
    settle_redraw(&spawned);
    let direct=display.shared.view.lock().unwrap().screen.clone();
    assert_eq!(direct.cursor,Some((0,10)));
    let cell=Size{width:9.0,height:17.0};
    let window=Window;
    let view=|process_finished,focused| Remote{display:Some(display),process_finished,focus:Focus(focused)}
        .render_screen(cell,color,black,&window).unwrap();
    let focus=view(false,true);
    let outline=view(false,false);
    let hidden=view(true,true);
    let after=display.shared.view.lock().unwrap().screen.clone();
    assert_eq!(Screen::clone(&direct),Screen::clone(&after));
    let rows=direct.rows.len();
    assert_eq!(focus.children.len(),rows+1);
    assert_eq!(outline.children.len(),rows+1);
    assert_eq!(hidden.children.len(),rows);
    assert_eq!(focus.children[..rows],hidden.children);
    assert_eq!(outline.children[..rows],hidden.children);
    let style=&hidden.children[0].children[1];
    assert_eq!(style.text.as_deref(),Some("color"));
    assert_eq!(style.fg,Some(rgb(0x010203)));
    assert_eq!(style.bg,Some(rgb(0x112163)));
    assert!(style.bold && style.italic && style.underline && style.strike);
    assert_eq!(style.x,45.0);
    let cursor=&focus.children[rows];
    assert_eq!((cursor.x,cursor.y,cursor.w,cursor.h),(98.0,8.0,9.0,17.0));
    assert_eq!(cursor.bg,Some(color.opacity(0.55)));
    assert_eq!(cursor.outline,None);
    let cursor=&outline.children[rows];
    assert_eq!(cursor.bg,None);
    assert_eq!(cursor.outline,Some(color.opacity(0.6)));
    assert!(cursor.border);
    assert!(Remote{display:None,process_finished:false,focus:Focus(true)}.render_screen(cell,color,black,&window).is_none());
    let local_started=Local{state:State::Running(Source(&direct)),focus:Focus(false)}
        .render_screen(cell,color,black,&window);
    let local_exited=Local{state:State::Exited(Source(&direct)),focus:Focus(true)}
        .render_screen(cell,color,black,&window);
    assert_eq!(local_started.children,[outline]);
    assert_eq!(local_exited.children,[hidden.clone()]);
    let mut absent_cursor=Screen::clone(&direct);
    absent_cursor.cursor=None;
    let local_cursorless=Local{state:State::Running(Source(&absent_cursor)),focus:Focus(true)}
        .render_screen(cell,color,black,&window);
    assert_eq!(local_cursorless.children,[hidden]);
    println!("\nTRACE cursor: running fill/outline and exact row geometry; transport-finished hides cursor without mutating cached screen; local and cursorless behavior unchanged");
}
