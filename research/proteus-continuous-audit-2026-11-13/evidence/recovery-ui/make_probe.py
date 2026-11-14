#!/usr/bin/env python3
"""Exact Desktop lifecycle bodies with a minimal inert GPUI shell.
No Desktop production source is edited; no OS process or user data is touched.
"""
import hashlib,json,pathlib,subprocess,sys
ROOT=pathlib.Path(sys.argv[1]).resolve()
HERE=pathlib.Path(__file__).resolve().parent
path='src/ui/extensions/declarative/runtime.rs'
source=subprocess.check_output(['git','-C',str(ROOT),'show','HEAD:'+path],text=True)
sha=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
def extract(marker):
    start=source.index(marker); p=source.index('{',start); end=p+1; n=1
    while n:
        n+=(source[end]=='{')-(source[end]=='}');end+=1
    code=source[start:end]
    return code,dict(path=path,start_line=source[:start].count('\n')+1,end_line=source[:end].count('\n')+1,sha256=hashlib.sha256(code.encode()).hexdigest())
observer,o=extract('|this, cx| {')
stop,s=extract('    fn stop(')
restart,r=extract('    pub(super) fn restart(')
# Attach's decision uses exactly this final production branch; all native view
# construction above it is irrelevant to whether an attempted launch occurs.
attach,a=extract('        if self.process.is_some() {')
shim=r'''
#![allow(dead_code)]
use std::{collections::{HashMap,VecDeque},marker::PhantomData};
struct Context<T>{enabled:bool,notifies:usize,render_generation:usize,_t:PhantomData<T>}
impl<T> Default for Context<T>{fn default()->Self{Self{enabled:true,notifies:0,render_generation:0,_t:PhantomData}}}
impl<T> Context<T>{fn notify(&mut self){self.notifies+=1;}}
#[derive(Clone,Copy)]enum Reset{Restart,Stop}
#[derive(Default)]struct Lifetime;
impl Lifetime{fn allowed(&self,enabled:bool)->bool{enabled}}
#[derive(Default)]struct Queue{resets:usize}
impl Queue{fn reset(&mut self){self.resets+=1;}}
struct View;
impl View{fn reset(&mut self,_:Reset,_:&mut Context<View>) {}}
struct WeakView;
impl WeakView{fn upgrade(&self)->Option<ViewEntity>{None}}
struct ViewEntity;
impl ViewEntity{fn update(&self,_:&mut Context<runtime::Runtime>,f:impl FnOnce(&mut View,&mut Context<View>)){f(&mut View,&mut Context::default());}}
struct Attached{view:WeakView,queue:Queue}
fn is_enabled(_: &str,cx: &Context<runtime::Runtime>)->bool{cx.enabled}
fn bump_render_generation(cx:&mut Context<runtime::Runtime>){cx.render_generation+=1;}
mod scopes{#[derive(Default)]pub struct EventCursor;}
mod declarative{
 pub mod runtime{
  use super::super::*;
  #[derive(Default)]pub struct Runtime{
    generation:u64, settings:VecDeque<String>, settings_bytes:usize,
    session_events:scopes::EventCursor, popup_closed:u64,process:Option<()>,
    _pump:Option<()>,views:HashMap<String,Attached>,error:Option<String>,
    lifetime:Lifetime,theme_context:Option<usize>,
    start_attempts:usize,render_calls:usize,scope_resets:usize
  }
  impl Runtime{
    fn extension_id(&self)->&str{"synthetic"}
    fn content_context(&self,_:&Context<Self>)->usize{1}
    fn invalidate_content(&mut self,_:&Context<Self>){}
    fn invalidate_preview(&mut self,_:&Context<Self>){}
    fn reset_scopes(&mut self){self.scope_resets+=1;}
    // Only admission is measured. Native subprocess launch is NOT simulated as
    // successful and no claim is made about GPUI scheduler/window behavior.
    fn start(&mut self,_:&mut Context<Self>){self.start_attempts+=1;}
    fn render(&mut self,_:&str,_:&Context<Self>){self.render_calls+=1;}
'''
methods='\n'.join([stop,restart])
observer_body=observer[observer.index('{')+1:-1]
# Exact branch from attach needs the else's from the following source too.
attach_marker='        if self.process.is_some() {\n            self.render(&view, cx);\n        } else if self.error.is_none() {\n            self.start(cx);\n        }'
assert attach_marker in source
branch_start=source.index(attach_marker)
a=dict(path=path,start_line=source[:branch_start].count('\n')+1,end_line=source[:branch_start+len(attach_marker)].count('\n')+1,sha256=hashlib.sha256(attach_marker.encode()).hexdigest())
methods+='\nfn preferences_changed(&mut self,cx:&mut Context<Self>){let this=self;'+observer_body+'\n}\n'
methods+='fn attach_decision(&mut self,cx:&mut Context<Self>){let view=String::from("new-panel");'+attach_marker+'\n}\n'
tests=r'''
  }
  #[cfg(test)]mod tests{
    use super::*;
    fn failed()->(Runtime,Context<Runtime>){
      let mut runtime=Runtime::default();
      // Exact postcondition of Signal::Exited. The message is synthetic.
      runtime.process=None;runtime.error=Some("fixture process exited".into());
      (runtime,Context::default())
    }
    fn toggle(runtime:&mut Runtime,cx:&mut Context<Runtime>){
      cx.enabled=false;runtime.preferences_changed(cx);
      cx.enabled=true;runtime.preferences_changed(cx);
    }
    #[test]fn observed_crash_error_survives_disable_enable_and_new_surface(){
      let(mut runtime,mut cx)=failed();toggle(&mut runtime,&mut cx);
      assert_eq!(runtime.start_attempts,0);
      assert_eq!(runtime.error.as_deref(),Some("fixture process exited"));
      assert_eq!(runtime.generation,1);
      runtime.attach_decision(&mut cx);
      assert_eq!(runtime.start_attempts,0);
      println!("failed -> disable -> enable -> new panel: start_attempts=0; old error retained");
    }
    #[test]fn control_healthy_toggle_admits_restart(){
      let(mut runtime,mut cx)=(Runtime::default(),Context::default());
      runtime.process=Some(());toggle(&mut runtime,&mut cx);
      assert_eq!(runtime.start_attempts,1);assert!(runtime.error.is_none());
      println!("healthy -> disable -> enable: start_attempts=1");
    }
    #[test]fn control_explicit_restart_clears_failure_and_admits_start(){
      let(mut runtime,mut cx)=failed();runtime.restart(&mut cx);
      assert_eq!(runtime.start_attempts,1);assert!(runtime.error.is_none());
      assert_eq!(cx.render_generation,1);
      println!("failed -> explicit Restart: start_attempts=1; error=None");
    }
    #[test]fn observed_protocol_error_while_process_alive_also_blocks_reenable(){
      let(mut runtime,mut cx)=failed();runtime.process=Some(());
      toggle(&mut runtime,&mut cx);
      assert_eq!(runtime.start_attempts,0);assert!(runtime.process.is_none());
      assert!(runtime.error.is_some());
      println!("live process + protocol error -> disable -> enable: start_attempts=0");
    }
    #[test]#[ignore]fn required_explicit_reenable_attempts_to_recover_failed_process(){
      let(mut runtime,mut cx)=failed();toggle(&mut runtime,&mut cx);
      assert_eq!(runtime.start_attempts,1,"explicit off/on must attempt fresh launch rather than retain old failure forever");
    }
  }
 }
}
use declarative::runtime;
'''
(HERE/'recovery_probe.rs').write_text(shim+methods+tests)
(HERE/'source-extractions.json').write_text(json.dumps({'desktop_sha':sha,'method':'git show HEAD, exact copied bodies; inert GPUI shell','functions':[o,s,r,a]},indent=2)+'\n')
