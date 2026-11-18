"""Independent interrupted-key controls built on the author's element/dispatch stand-ins."""
from pathlib import Path
import sys,subprocess,tempfile
root=Path(sys.argv[1]); rust=sys.argv[2]
stub=(Path(__file__).parent/'events.rs.in').read_text()
def body(text,sig):
    start=text.index(sig); b=text.index('{',start)
    depth=0
    for i in range(b,len(text)):
        if text[i]=='{':depth+=1
        if text[i]=='}':
            depth-=1
            if not depth:return text[start:i+1]
    raise ValueError(sig)
div=(root/'before/vendor/gpui-fast/src/elements/div.rs').read_text(); wnd=(root/'before/vendor/gpui-fast/src/window.rs').read_text()
lo=div.index('window.on_key_event({',div.index('// Record the focus generation at which an enter/space key'))
hi=div.index('\n                }\n',lo)
stub=stub.replace('/*BUTTON*/',div[lo:hi]).replace('/*DISPATCH*/',body(wnd,'fn dispatch_key_down_up_event('))
stub=stub[:stub.index('fn main(){')]
stub=stub.replace('key:&str,mods:Modifiers,repeat:usize','genchange:bool, interrupt:bool, prevent:bool')
stub=stub.replace('struct Window {rendered_frame:', 'struct Window {prevent:bool,rendered_frame:')
stub=stub.replace('Window{rendered_frame:', 'Window{prevent:false,rendered_frame:')
stub=stub.replace('fn default_prevented(&self)->bool{false}', 'fn default_prevented(&self)->bool{self.prevent}')
a=stub.index('    let stroke=Stroke{key:key.into()')
b=stub.index('    let cursor=model.borrow()',a)
stub=stub[:a]+'''
    let mk=|key:&str|Stroke{key:key.into(),modifiers:Modifiers::default()};
    w.prevent=prevent;
    cx.propagate_event=true; w.dispatch_key_down_up_event(&KeyDownEvent{keystroke:mk("enter")},&vec![0,1],&mut cx);
    w.prevent=false;
    if genchange { w.focus_generation+=2; } // Departed and returned to same focus id; generation still differs.
    if interrupt {cx.propagate_event=true; w.dispatch_key_down_up_event(&KeyDownEvent{keystroke:mk("q")},&vec![0,1],&mut cx);}
    cx.propagate_event=true; w.dispatch_key_down_up_event(&KeyUpEvent{keystroke:mk("enter")},&vec![0,1],&mut cx);
''' +stub[b:]
stub+='''
fn main(){
 let before=std::env::args().nth(1).unwrap()=="before";
 let mut cases=0;let mut mismatches=0;
 for role in [Role::Back,Role::SearchButton,Role::List,Role::Field]{for n in [0,1,4usize]{for at in 0..n.max(1){for aba in [false,true]{for itr in [false,true]{for no_default in [false,true]{
 let got=run(role,n,at,aba,itr,no_default);
 let header=matches!(role,Role::Back|Role::SearchButton);
 let ok=header&&!aba&&!itr&&!no_default;
 let picked=if !header&&n>0 {vec![n+9-at]}else{vec![]};
 cases+=1;
 if (got.open,got.back,&got.picks)!=(usize::from(ok&&role==Role::SearchButton),usize::from(ok&&role==Role::Back),&picked){mismatches+=1;}
 }}}}}}
 println!("interrupted activation matrix: {cases} cases, {mismatches} mismatches; before={before}");
 if before{assert!(mismatches>0);}else{assert_eq!(mismatches,0);}
}
'''
with tempfile.TemporaryDirectory() as tmp:
 for phase in ['before','after']:
    src=(root/phase/'src/ui/picker.rs').read_text(); o=Path(tmp)/phase
    s=stub
    for token,sig in [('KEYS','fn keys('),('CURRENT','fn current('),('FOCUS','pub fn search_focus(')]:s=s.replace(f'/*{token}*/',body(src,sig))
    code=o.with_suffix('.rs');code.write_text(s);subprocess.run([rust,'-Awarnings','--edition=2024',str(code),'-o',str(o)],check=True);subprocess.run([o,phase],check=True)
