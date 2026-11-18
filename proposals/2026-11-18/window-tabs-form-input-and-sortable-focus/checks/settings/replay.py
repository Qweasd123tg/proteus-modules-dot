from pathlib import Path
import argparse,subprocess as sp,tempfile
p=argparse.ArgumentParser()
for a in ['desktop','rustc','serde-json']:p.add_argument('--'+a,required=True)
args=p.parse_args()
base='src/ui/settings';ref='2307e9c67125bbe66f15ced51317a2dfcc437aa4'
def read(p):return sp.check_output(['git','--git-dir',args.desktop,'show',ref+':'+p],text=True)
def fun(s,n,lev=4):
 a=s.index('fn '+n+'(');return s[a:s.index('\n'+' '*lev+'}',a)+2+lev]
def build(d):
 s=Path(__file__).with_name('collector.rs.in').read_text()
 ed=(d/base/'editors.rs').read_text();ps=(d/base/'params.rs').read_text()
 sch=read('src/settings/schema.rs');assert 'FieldKind::Text(TextFormat::Json)' in sch and 'this.text_changed(&key, format, default.as_ref(), &text, cx);' in ed
 widgets=read(base+'/widgets.rs')
 assert 'move |_, _, cx| select(value.clone(), cx)' in widgets
 assert 'self.editors.fields.insert(' in ed and 'self.create_field(leaf, window, cx);' in ed
 assert 'kit::button(hashed_id("params-file"' in ps
 a=ps.index('                let json = self.is_json');b=ps.index('\n            });',a)
 modern='enum ParameterMode' in ed
 parts={'button':ps[a:b],'format':sch[sch.index('#[derive(Clone, Copy, Debug, PartialEq, Eq)]\npub enum TextFormat'):sch.index('impl TextFormat')],'parse':fun(sch,'parse_text',0),
 'module_key':fun(ed,'module_key',0),'forget':fun(ed,'forget_form'),'text_changed':fun(ed,'text_changed'),'json_error':fun(ed,'json_error'),
 'form_error':fun(ed,'form_error') if modern else '', 'mode':ed[ed.index('#[derive(Clone, Copy)]\npub(super) enum ParameterMode'):ed.index('pub(super) fn module_key')].replace('pub(super) enum','enum') if modern else '',
 'switch':fun(ed,'switch_mode' if modern else 'toggle_json')}
 for k,v in parts.items():s=s.replace('@@'+k+'@@',v)
 f=d/'main.rs';f.write_text(s);lib=Path(args.serde_json);out=d/'form'
 sp.run([args.rustc,'--edition=2021',str(f),'--extern','serde_json='+str(lib),'-L','dependency='+str(lib.parent),'-o',str(out)],check=True)
 return sp.run([out]).returncode
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/base).mkdir(parents=True)
 for n in ('editors','params'):
  f=base+'/'+n+'.rs';(d/f).write_text(read(f))
 print('upstream',flush=True);red=build(d)
 patch=Path(__file__).resolve().parents[2]/'patches/confirm-invalid-form-before-json.patch'
 sp.run(['git','apply','--check',str(patch)],cwd=d,check=True);sp.run(['git','apply',str(patch)],cwd=d,check=True)
 print('candidate',flush=True);green=build(d)
 sp.run(['git','apply','--check','--reverse',str(patch)],cwd=d,check=True)
 assert (red,green)==(1,0);print('expected red/green exits 1/0, forward/reverse apply clean')
