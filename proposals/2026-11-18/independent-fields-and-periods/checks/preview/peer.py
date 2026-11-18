#!/usr/bin/env python3
"""Independent focused Native Rust replay for retained UI ownership.
python peer.py DESKTOP_CHECKOUT [--rustc rustc] [--expect before|after]
Reads only UI presentation and ownership expressions. Does not build or launch Desktop."""
import argparse,re,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('desktop',type=Path);ap.add_argument('--rustc',default='rustc');ap.add_argument('--expect',choices=['before','after']);q=ap.parse_args()
root=q.desktop;sub=root/'src/ui/extensions/declarative'
fields=(sub/'fields.rs').read_text();ta=(sub/'fields/textarea.rs').read_text();render=(sub/'render.rs').read_text();fmt=(root/'src/ui/format.rs').read_text()
def cap(s,regex): return re.search(regex,s,re.S).group(1)
def fun(s,signature):
 i=s.index(signature);j=s.index('{',i);depth=1
 while depth: j+=1; depth+=(s[j]=='{')-(s[j]=='}')
 return s[i:j+1]
def require(s,*parts):
 for part in parts: assert part in s,part
owned='preview_open: bool,' in fields
if q.expect: assert owned==(q.expect=='after')
# Verify that focus/render routes that use these fields are present. This is not a GUI test.
require(ta,'state.read(cx).focus_handle(cx)','header.track_focus(&focus)','keyboard_focus.is_focused(window)','!event.keystroke.modifiers.modified()','"enter" | "space"','motion::preview_reveal(key, open, cx, preview, || area)','return area.into_any_element()')
require(render,'super::fields::textarea::render(', 'self.fields.disclosures.get(id).copied().unwrap_or(*open)','this.fields.disclosures.insert(id.clone(), !opened);')
require(fields,'self.fields.disclosures.entry(id.clone()).or_insert(*open);','if grow && textarea::preview(&state.read(cx).value()).is_some()')
prune=fun(fields,'pub(super) fn prune_fields(')
inc=cap(prune,r'Node::Input \{ id, \.\. \} => \{([^}]+)\}')
disc=cap(prune,r'Node::Disclosure \{ id, \.\. \} => \{([^}]+)\}')
retain=re.findall(r'(self\.fields\s*\.\s*(?:inputs|disclosures)\s*\.retain\([^;]+;)',prune);assert len(retain)==2
preview=fun(fmt,'pub fn editor_preview(')
limits='\n'.join(re.findall(r'const PREVIEW_(?:LINES|CHARS):[^;]+;',fmt)); assert '8' in limits
open_expr=cap(ta,r'let open = (.*?);')
click=cap(ta,r'on_click\(cx.listener.*?cx.emit\(WillResize\);\s*(.*?;)')
key=cap(ta,r'on_key_down\(cx.listener.*?cx.emit\(WillResize\);\s*(.*?;)')
edit=cap(fields,r'if grow && textarea::preview\(&state.read\(cx\).value\(\)\).is_some\(\) \{\s*(.*?;)')
if owned:
 helper=fun(fields,'fn set_input_preview('); ids=''; name='let input_id=id.to_owned();let keyboard_id=id.to_owned();'
 require(fields,'preview_open: false,'); require(ta,'extension-input-{}-input-preview:{id}'); assert 'disclosure_id(' not in ta
else:
 helper=''; ids=fun(ta,'pub(super) fn disclosure_id('); name='let id=textarea::disclosure_id(id);let input_id=id.clone();let keyboard_id=id.clone();'
 require(ta,'let id = disclosure_id(id);','extension-input-{}-{id}')
template=r'''
#![allow(unused_variables,dead_code)]
use std::collections::{HashMap,HashSet};
mod textarea { /*IDS*/ }
/*LIMITS*/
/*PREVIEW*/
#[derive(Default)] struct Input {preview_open:bool}
#[derive(Default)] struct Fields {inputs:HashMap<String,Input>, disclosures:HashMap<String,bool>}
impl Fields {/*HELPER*/}
#[derive(Default)]struct View {fields:Fields}
const I:&str="note";
const D:&str="input-preview:note";
impl View {
fn change_tree(&mut self, has_i:bool,has_d:bool,default_open:bool) {
 let mut ids:HashSet<(usize,String)>=HashSet::new();
 if has_i {let id=&I.to_string(); /*INC*/}
 if has_d {let id=&D.to_string(); /*DISC*/}
 /*RETAIN*/
 if has_i {self.fields.inputs.entry(I.into()).or_default();}
 if has_d {let id=&D.to_string();let open=&default_open; self.fields.disclosures.entry(id.clone()).or_insert(*open);}
}
fn p(&self)->bool {let view=self;let id=I;/*NAME*/ /*OPEN*/}
fn d(&self)->bool {self.fields.disclosures[D]}
fn ui(&mut self,which:u8) {let id=I;let open=self.p();let view=self;/*NAME*/match which {
 1=>{/*CLICK*/}, 2=>{if !open{/*KEY*/}}, _=>{}
}}
fn edit(&mut self) {let this=self;let input_id=I.to_string();let text="field content\n".repeat(12);if editor_preview(text.chars()).is_some(){/*EDIT*/}}
fn hit_d(&mut self) {let id=D.to_owned();let opened=self.d();let this=self;this.fields.disclosures.insert(id.clone(),!opened);}
}
fn main(){
 let mut bad=[0;6];let mut checks=[0;6];
 for def in [false,true] {for first in [0u8,1,2,3]{for second in [0u8,1,2,3]{
 let mut v=View::default();v.change_tree(true,true,def);let mut p=false;let mut d=def;
 let eq=|index:usize,pass:bool,bad:&mut [u32;6],checks:&mut [u32;6]|{checks[index]+=1;bad[index]+=(!pass) as u32;};
 eq(0,v.p()==p && v.d()==d,&mut bad,&mut checks);
 for op in [first,second]{match op {
  0=>{v.hit_d();d=!d;}, 1=>{v.ui(1);p=!p;}, 2=>{v.ui(2);p=true;}, _=>{v.edit();p=true;} }
  eq(1,v.p()==p && v.d()==d,&mut bad,&mut checks);
 }
 // Changing a public default during a retained control must not overwrite the user's choice.
 v.change_tree(true,true,!def);eq(2,v.p()==p && v.d()==d,&mut bad,&mut checks);
 // Retained preview does not confer lifetime on a removed public Disclosure.
 v.change_tree(true,false,def);v.change_tree(true,true,!d);
 eq(3,v.p()==p && v.d()!=d,&mut bad,&mut checks);
 // Retained disclosure does not keep a removed editor's old preview flag.
 let kept=v.d();v.change_tree(false,true,def);v.change_tree(true,true,def);
 eq(4,!v.p()&&v.d()==kept,&mut bad,&mut checks);
 // Both are recreated: default belongs to the disclosure, never the preview.
 v.change_tree(false,false,def);v.change_tree(true,true,true);
 eq(5,!v.p()&&v.d(),&mut bad,&mut checks);
 }}}
 println!("checks={checks:?}; violations={bad:?} [initial, event isolation, retained defaults, remount disclosure, remount input, remount both]");
 assert_eq!(bad.iter().all(|n|*n==0),/*OWNED*/);
}'''
for k,v in dict(IDS=ids,HELPER=helper,PREVIEW=preview,LIMITS=limits,INC=inc,DISC=disc,RETAIN='\n'.join(retain),NAME=name,OPEN=open_expr,CLICK=click,KEY=key,EDIT=edit,OWNED=str(owned).lower()).items():
 template=template.replace('/*'+k+'*/',v)
with tempfile.TemporaryDirectory() as d:
 d=Path(d);rs=d/'replay.rs';rs.write_text(template);subprocess.run([q.rustc,'--edition=2024',str(rs),'-o',str(d/'test')],check=True);subprocess.run([str(d/'test')],check=True)
