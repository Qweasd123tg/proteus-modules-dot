#![allow(dead_code)]
mod diff;
use diff::{File,FileInfo,Pair,Kind};
use std::sync::Arc;
use std::rc::Rc;
#[allow(unused_imports)] use std::collections::{HashMap,HashSet};
use std::cell::Cell;
use std::ops::Range;
use std::marker::PhantomData;
#[derive(Clone,Default,Debug)] struct ListState;
#[derive(Clone,Copy,Default)] struct ListOffset { item_ix:usize, offset_in_item:f32 }
impl ListState {fn logical_scroll_top(&self)->ListOffset{Default::default()}fn remeasure_items(&self,_:Range<usize>){}fn splice(&self,_:Range<usize>,_:usize){}fn item_count(&self)->usize{0}fn scroll_to(&self,_:ListOffset){}}
type HighlightStyle=u64;
#[derive(Clone)] struct HighlightTheme(u64);
struct Theme { highlight_theme:Arc<HighlightTheme> }
struct Context<T> {t:Theme,next:usize,_unused:PhantomData<T>}
impl<T> Context<T>{fn theme(&self)->&Theme{&self.t}fn focus_handle(&mut self)->usize{self.next+=1;self.next}fn notify(&self){}}
thread_local! { static UPDATES:Cell<usize>=const{Cell::new(0)}; static SHAPES:Cell<usize>=const{Cell::new(0)}; }
thread_local!{static GENERATION:Cell<u64>=const{Cell::new(0)};}
struct LanguageRegistry;impl LanguageRegistry{fn singleton()->Self{Self}fn generation(&self)->u64{GENERATION.get()}}
@@REVISION@@
struct Rope(String);impl Rope{fn from_str(s:&str)->Self{Self(s.to_owned())}}
struct SyntaxHighlighter{lang:String,source:String}
impl SyntaxHighlighter{
 fn new(lang:&str)->Self{Self{lang:lang.into(),source:String::new()}}
 fn update(&mut self,_:Option<()>,src:&Rope,_opt:Option<()>) {UPDATES.set(UPDATES.get()+1);self.source.clone_from(&src.0)}
 // Deterministic stand-in for a third-party highlighter. The style captures the
 // entire source, selected language and theme. All range projection is real.
 fn styles(&self,range:&Range<usize>,theme:&HighlightTheme)->Vec<(Range<usize>,HighlightStyle)>{
   assert_eq!(range.end,self.source.len());
   let val=self.lang.bytes().chain([255]).chain(self.source.bytes()).fold(theme.0.wrapping_add(GENERATION.get()),|v,b|v.wrapping_mul(31).wrapping_add(b as u64));
   if range.is_empty(){vec![]}else{vec![(range.clone(),val)]}
 }
}
mod syntax {use super::*; @@SYNTAX@@ }
type SharedString=String;
struct Window;struct FontSys;struct Shaped(f32);impl Shaped{fn width(self)->f32{self.0}}
impl Window{fn text_system(&self)->FontSys{FontSys}}
impl FontSys{fn shape_line(&self,s:String,_size:f32,_runs:&[usize],_meta:Option<()>)->Shaped{SHAPES.set(SHAPES.get()+1);Shaped(s.chars().count() as f32)}}
fn px(n:f32)->f32{n}
struct DiffView{patch:String,info:Vec<FileInfo>,files:Vec<Rc<File>>,syntax:Vec<Rc<syntax::Syntax>>,syntax_theme:Arc<HighlightTheme>,syntax_revision:Option<u64>,list:Option<ListState>,horizontal:Vec<[usize;3]>,file_focus:Vec<usize>,folded:HashSet<String>,measured:Option<()>,}
impl DiffView{
 fn resized(&self,_:&Context<Self>){}
 @@SET_PATCH@@
 fn render_theme(&mut self,cx:&mut Context<Self>){ @@RENDER_THEME@@ }
 fn widths(&self)->Vec<f32>{let window=Window;let font_size=12.;let run=|len|len;@@WIDTHS@@ widths}
}
fn view(cx:&Context<DiffView>)->DiffView{DiffView{patch:String::new(),info:vec![],files:vec![],syntax:vec![],syntax_theme:cx.theme().highlight_theme.clone(),syntax_revision:SyntaxHighlighter::language_revision(),list:Some(ListState),horizontal:vec![],file_focus:vec![],folded:HashSet::new(),measured:None}}
fn block(path:&str,value:&str)->String{format!("diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@ unchanged heading\n-old\n+{value}\n")}
fn assembled(rows:&[(String,String)])->String{rows.iter().map(|(p,v)|block(p,v)).collect()}
fn check(v:&DiffView){
 for (i,f) in v.files.iter().enumerate(){
   let fresh=syntax::Syntax::new(f,&v.syntax_theme);
   for n in 0..f.lines.len(){for old in [true,false]{assert_eq!(fresh.line(n,old),v.syntax[i].line(n,old))}}
   let mut shown=HashSet::new();
   for pair in &f.pairs{match pair {Pair::Full(k)=>{shown.insert(*k);},Pair::Lines(a,b)=>{shown.extend([*a,*b].into_iter().flatten());}}}
   assert_eq!(shown,f.unified.iter().copied().collect());
 }
}
fn refresh(v:&mut DiffView,cx:&mut Context<DiffView>,patch:&str,info:&[FileInfo],expected:usize){
 let old_paths=v.files.iter().map(|f|f.path.clone()).collect::<Vec<_>>();
 let old_focus=v.file_focus.clone();let old_pos=v.horizontal.clone();
 let early=v.patch==patch && v.info==info;
 UPDATES.set(0);v.set_patch(patch,info,cx);v.render_theme(cx);
 if early {assert_eq!(v.file_focus,old_focus);assert_eq!(v.horizontal,old_pos);}
 else {for (i,f) in v.files.iter().enumerate(){
    if let Some(k)=old_paths.iter().position(|p|p==&f.path){assert_eq!(v.file_focus[i],old_focus[k]);assert_eq!(v.horizontal[i],old_pos[k]);}
    else{assert!(!old_focus.contains(&v.file_focus[i]));assert_eq!(v.horizontal[i],[0;3]);}
 }}
assert_eq!(UPDATES.get(),expected);check(v);
}
fn main(){
 let revised=std::env::args().any(|s|s=="revised"); let nothing=std::env::args().any(|s|s=="untracked");
 let indexed=revised||std::env::args().any(|s|s=="indexed");
 let candidate=indexed||std::env::args().any(|s|s=="candidate");
 let reuse=candidate && !nothing;
 let mut cx=Context{t:Theme{highlight_theme:Arc::new(HighlightTheme(1))},next:0,_unused:PhantomData};
 let base=|before,after|if reuse {after}else{before};
 for n in [1usize,16,256]{
  let mut v=view(&cx);let mut rows:Vec<_>=(0..n).map(|i|(format!("f{i}.rs"),format!("let answer={i};"))).collect();
  refresh(&mut v,&mut cx,&assembled(&rows),&[],2*n);
  rows[n/2].1.push('!');refresh(&mut v,&mut cx,&assembled(&rows),&[],base(2*n,2));
  println!("{n} files, one content change: {} highlighter.update calls",base(2*n,2));
  refresh(&mut v,&mut cx,&assembled(&rows),&[],0);
  rows.push(("new.py".into(),"new = True".into()));refresh(&mut v,&mut cx,&assembled(&rows),&[],base(2*(n+1),2));
  let meta=vec![FileInfo{path:"new.py".into(),status:"changed".into(),message:None}];refresh(&mut v,&mut cx,&assembled(&rows),&meta,base(2*(n+1),2));
  cx.t.highlight_theme=Arc::new(HighlightTheme(2));refresh(&mut v,&mut cx,&assembled(&rows),&meta,2*(n+1));
  cx.t.highlight_theme=Arc::new(HighlightTheme(3));rows[0].1.push('?');refresh(&mut v,&mut cx,&assembled(&rows),&meta,2*(n+1));
  if revised && !nothing {
    GENERATION.set(GENERATION.get()+1);refresh(&mut v,&mut cx,&assembled(&rows),&meta,2*(n+1));
    GENERATION.set(GENERATION.get()+1);rows[n/2].1.push('!');refresh(&mut v,&mut cx,&assembled(&rows),&meta,2*(n+1));
  }
  let last=rows.len()-1;rows.swap(0,last);refresh(&mut v,&mut cx,&assembled(&rows),&meta,if indexed && reuse {0}else{base(2*(n+1),4)});
  if n == 256 { println!("256 ordinary unchanged paths: old two position scans require 2*(1+...+256) = 65792 equality checks; indexed version builds 256 entries and looks up 256 paths"); }
 }
 let mut v=view(&cx);
 let duplicate=[("same.rs".into(),"first".into()),("same.rs".into(),"second".into())];refresh(&mut v,&mut cx,&assembled(&duplicate),&[],4);
 v.horizontal[0]=[1,2,3];v.horizontal[1]=[7,8,9];assert_ne!(v.file_focus[0],v.file_focus[1]);
 let mut switched=duplicate.clone();switched.swap(0,1);refresh(&mut v,&mut cx,&assembled(&switched),&[],if indexed && reuse {2}else{4});
 refresh(&mut v,&mut cx,include_str!("normal.diff"),&[],2);SHAPES.set(0);let w=v.widths()[0];
 println!("ordinary git diff: widest measured row {w} ASCII columns, {} text measurements",SHAPES.get());
 let f=&v.files[0];let visible=f.unified.iter().map(|&i|f.lines[i].text.chars().count()).max().unwrap();
 if candidate {assert_eq!(w,visible as f32)}else{assert!(w>7.*visible as f32)}
 let marker="diff --git a/p b/p\n--- a/p\n+++ b/p\n@@ -1 +1 @@ long function heading\n-abc\n+\t12345\n\\ No newline at end of file\n";
 refresh(&mut v,&mut cx,marker,&[],2);let got=v.widths()[0];assert!(got>=("    12345  Нет перевода строки".chars().count()) as f32);
 let note=[FileInfo{path:"picture.png".into(),status:"added".into(),message:Some("A long binary note that must remain visible".into())}];refresh(&mut v,&mut cx,"",&note,2);assert_eq!(v.widths()[0],note[0].message.as_ref().unwrap().len() as f32);
 if revised {println!("registry revision: {:?}",SyntaxHighlighter::language_revision());}
 println!("Old/new sides equal fresh output after full/partial replacement, append, changed metadata, reordered or duplicate paths and theme swaps; visible note/tab/no-newline widths retained.");
}
