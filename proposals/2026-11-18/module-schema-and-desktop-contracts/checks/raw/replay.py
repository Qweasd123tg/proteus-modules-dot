from pathlib import Path
import tempfile,subprocess as sp,argparse
p=argparse.ArgumentParser();p.add_argument('--desktop',required=True);p.add_argument('--rustc',default='rustc');a=p.parse_args()
base='src/ui/settings';ref='2307e9c67125bbe66f15ced51317a2dfcc437aa4'
def git(p):return sp.check_output(['git','--git-dir',a.desktop,'show',ref+':'+p+'.rs'],text=True)
def fn(s,name,lev=4):
 i=s.index('fn '+name+'(');j=s.index('\n'+' '*lev+'}',i);return s[i:j+2+lev]
def run(d):
 s=Path(__file__).with_name('probe.rs.in').read_text()
 rd=lambda n:(d/base/(n+'.rs')).read_text()
 sea,spott,par=rd('search'),rd('spot'),rd('params');ed=git(base+'/editors');cat=git('src/settings/catalog');draft=git('src/settings/draft');sch=git('src/settings/schema')
 assert 'self.go_to(' not in sea
 assert 'this.go_to(&hit.target, window, cx)' in git(base+'/nav') and 'self.open.extend(hit.open.iter().cloned());' in spott
 assert 'self.spotted(\n            &super::spot::field(path)' in git(base+'/fields') and 'self.spotted(&super::spot::field(path)' in git(base+'/group')
 assert 'self.search_params(snapshot, finder, slot, module, &page, &place, &[]);' in sea
 assert 'self.params_section(slot, &module, cx)' in git(base+'/slots')
 dest=spott[spott.index('#[derive(Clone, Debug, PartialEq, Eq)]\npub(super) struct Destination'):spott.index('pub(super) struct Spot')].replace('pub(super)','pub(crate)')
 scope=sea[sea.index('struct Scope<'):sea.index('#[cfg(test)]\nmod tests',sea.index('struct Scope<'))]
 parts={'path':'\n'.join(fn(draft,k) for k in ('new','child','dotted')), 'scope_key':'pub(super) '+fn(sch,'section_scope',0),
 'editable':'\n'.join(fn(cat,k,0) for k in ('editable_fields','editable_field')), 'destination':dest, 'field_key':'pub(super) '+fn(spott,'field',0),
 'json_key':'pub(super) '+fn(spott,'params_json',0) if 'fn params_json' in spott else '', 'finder':sea[sea.index('const LIMIT:'):sea.index('/// Russian names')].replace('pub(super)','pub(crate)'),
 'scope':scope.replace('crate::settings','settings'), 'is_json':fn(ed,'is_json'),'search_params':fn(sea,'search_params'),
 'params_body':fn(par,'params_body').replace('super::spot::','spot::')}
 for k,v in parts.items():s=s.replace('@@'+k+'@@',v)
 f=d/'test.rs';f.write_text(s);exe=d/'probe';sp.run([a.rustc,'--edition=2024','-Awarnings',str(f),'-o',str(exe)],check=True);return sp.run([exe]).returncode
with tempfile.TemporaryDirectory() as t:
 d=Path(t);(d/base).mkdir(parents=True)
 for f in ['search','params','spot']:(d/base/(f+'.rs')).write_text(git(base+'/'+f))
 print('UPSTREAM',flush=True);red=run(d);patch=Path(__file__).resolve().parents[2]/'patches/desktop/raw-settings-search-target.patch'
 sp.run(['git','apply','--check',str(patch)],check=True,cwd=d);sp.run(['git','apply',str(patch)],check=True,cwd=d)
 print('CANDIDATE',flush=True);green=run(d)
 sp.run(['git','apply','--reverse','--check',str(patch)],check=True,cwd=d)
 assert (red,green)==(1,0);print('forward/reverse apply clean; exits 1 -> 0')
