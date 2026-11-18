"""Native projections on public schema values. Input is immutable source, not a live profile."""
from pathlib import Path
import argparse,tempfile,subprocess as sp
p=argparse.ArgumentParser()
for v in ['desktop','core','deps']:p.add_argument(v,type=Path)
p.add_argument('--rustc',default='rustc');a=p.parse_args()
r=a.desktop;rd=lambda n:(r/n).read_text()
src=rd('src/ui/settings/search.rs');spot=rd('src/ui/settings/spot.rs');g=rd('src/ui/settings/group.rs');params=rd('src/ui/settings/params.rs');df=rd('src/settings/draft.rs');sch=rd('src/settings/schema.rs');fields=rd('src/ui/settings/fields.rs');catalog=rd('src/settings/catalog.rs')
def between(s,b,e):i=s.index(b);return s[i:s.index(e,i)]
def fun(s,name):
 i=s.index('fn '+name+'(');start=s.index('{',i);j=start+1;n=1
 while n:n+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[i:j]
core=(a.core/'crates/proteus-contracts/src/domain/config_schema.rs').read_text()
dto=between(core,'#[derive(Debug, Clone, Default, Serialize','impl ConfigField')
modern='fn form_scope(' in sch
scope=between(src,"struct Scope<'", '#[cfg(test)]\nmod tests').replace('crate::settings::','super::settings::')
assert 'let Some(spot) = self.spot.as_ref().filter(|spot| spot.key == key)' in spot
assert 'self.open.extend(hit.open.iter().cloned());' in spot and 'self.spotted(' in fields and 'spot::field(path)' in fields and 'self.spotted(&super::spot::field(path)' in g
assert 'let key = format!("advanced:{scope}");' in g and 'let open = self.is_open(&key);' in g and 'let toggle_key = key.clone()' in g
assert 'field_sections(fields)' in g and 'section_scope(scope, section.fields[0])' in g
expr=between(g,'        let scope =','        let open = self.is_open(&key);').strip()
root='crate::settings::form_scope(slot, module, &[])' if modern else 'format!("{slot}:{module}")'
assert '&'+root in params
parts={'MODERN':str(modern).lower(),'DTO':dto,'EDIT':fun(catalog,'editable_field')+'\n'+fun(catalog,'editable_fields'),'BUILD':fun(df,'new')+'\n'+fun(df,'child')+'\n'+fun(df,'dotted'),'SCOPEKEY':((fun(sch,'push_scope_part')+'\npub '+fun(sch,'form_scope')+'\n') if modern else '')+'pub '+fun(sch,'section_scope'),'FIELD':'pub '+fun(spot,'field'),'HIT':between(src,'const LIMIT:','/// Russian names'),'SCOPE':scope,'GROUP':expr,'ROOT':root}
s=Path(__file__).with_name('frame.rs.in').read_text()
for k,v in parts.items():s=s.replace('/*'+k+'*/',v)
with tempfile.TemporaryDirectory() as t:
 t=Path(t);f=t/'main.rs';f.write_text(s);cmd=[a.rustc,'--edition=2024','-Awarnings','-L','dependency='+str(a.deps)]
 for n in ['serde','serde_json']:lib,=a.deps.glob('lib'+n+'-*.rlib');cmd+=['--extern',n+'='+str(lib)]
 sp.run(cmd+[f,'-o',t/'test'],check=True);sp.run([t/'test'],check=True)
