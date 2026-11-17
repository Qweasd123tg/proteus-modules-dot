// Type and geometry stand-ins, not a real drawing or layout engine.
// The hex-only leaf keeps exact RGBA bytes; it does not model all color formats.
type Result<T> = std::result::Result<T,Box<dyn std::error::Error>>;
macro_rules! anyhow{($($t:tt)*)=>{Box::<dyn std::error::Error>::from(format!($($t)*))};}
#[derive(Clone,Copy,Debug,PartialEq)] struct Hsla(u32);
#[derive(Clone,Copy,Debug,PartialEq)] struct LinearColorStop{color:Hsla,percentage:f32}
#[derive(Clone,Copy,Debug,PartialEq)] enum Background{Solid(Hsla),Gradient(f32,LinearColorStop,LinearColorStop)}
#[derive(Clone,Copy,Debug,PartialEq)] enum Fill{Color(Background)}
impl From<Hsla> for Background{fn from(v:Hsla)->Self{Self::Solid(v)}}
impl From<Hsla> for Fill{fn from(v:Hsla)->Self{Fill::Color(v.into())}}
fn try_parse_color(v:&str)->Result<Hsla>{let s=v.strip_prefix('#').ok_or("expected a hex leaf")?;
    let s=match s.len(){6=>format!("{s}ff"),8=>s.to_owned(),_=>return Err("bad leaf".into())};
    Ok(Hsla(u32::from_str_radix(&s,16)?))}
fn linear_color_stop(color:Hsla,percentage:f32)->LinearColorStop{LinearColorStop{color,percentage}}
fn linear_gradient(a:f32,b:LinearColorStop,c:LinearColorStop)->Background{Background::Gradient(a,b,c)}
#[derive(Clone,Copy)] struct ThemeToken{color:Hsla,background:Background}
impl ThemeToken{fn new(color:Hsla,background:Background)->Self{Self{color,background}}}
/* VENDOR */
type App=Theme;
#[derive(Clone,Copy)] struct Tokens{sidebar_accent:ThemeToken,list_hover:ThemeToken}
#[derive(Clone,Copy)] struct Theme{tokens:Tokens,sidebar_accent:Hsla,list_hover:Hsla,radius:f32}
impl Theme{fn theme(&self)->&Self{self}}
#[derive(Clone,Debug,Default,PartialEq)] struct Style{background:Option<Fill>}
#[derive(Clone,Debug,Default,PartialEq)] struct Div{st:Style,over:Option<Fill>,children:Vec<Div>}
fn div()->Div{Div::default()} fn px(v:f32)->f32{v}
mod prefs{pub fn scaled(v:f32)->f32{v}}
trait Styled:Sized{fn style(&mut self)->&mut Style;/* STYLE */}
impl Styled for Div{fn style(&mut self)->&mut Style{&mut self.st}}
impl Div{
    fn absolute(self)->Self{self}fn inset_0(self)->Self{self}fn top_0(self)->Self{self}fn bottom_0(self)->Self{self}
    fn left(self,_:f32)->Self{self}fn right(self,_:f32)->Self{self}fn top(self,_:f32)->Self{self}fn bottom(self,_:f32)->Self{self}
    fn rounded(self,_:f32)->Self{self}
    fn when(self,yes:bool,f:impl FnOnce(Self)->Self)->Self{if yes{f(self)}else{self}}
    fn child(mut self,d:Div)->Self{self.children.push(d);self}
    fn group_hover(mut self,_:&str,f:impl FnOnce(Self)->Self)->Self{self.over=f(div()).st.background;self}
}
/* PAINT */
fn main(){
    let args:Vec<String>=std::env::args().collect();
    let a=try_parse_theme_token(&args[1]).unwrap();let h=try_parse_theme_token(&args[2]).unwrap();
    let t=Theme{tokens:Tokens{sidebar_accent:a,list_hover:h},sidebar_accent:a.color,list_hover:h.color,radius:6.};
    let as_fill=|tok:ThemeToken|Some(Fill::Color(tok.background));
    let mut tests=0;let mut failures=0;
    let mut check=|scope:&str,got:Option<Fill>,want:Option<Fill>|{tests+=1;if got!=want{failures+=1;if failures<=3{println!("{scope}: got {got:?} expected {want:?}")}}};
    for selected in [false,true]{for cursor in [false,true]{for inset in [false,true]{
        let got=background(selected,cursor,"probe",inset,&t);
        check("row idle/cursor/selected",got.st.background,if selected{as_fill(a)}else if cursor{as_fill(h)}else{None});
        check("pointer overlay while not selected",got.over,if selected{None}else{as_fill(h)});
    }}}
    for selected in [false,true]{let r=menu_surface(selected,&t);
        check("committed menu choice",r.children.first().and_then(|c|c.st.background),if selected{as_fill(a)}else{None});}
    println!("selection state checks: {}/{}",tests-failures,tests);
    if failures>0{std::process::exit(1);}
}
