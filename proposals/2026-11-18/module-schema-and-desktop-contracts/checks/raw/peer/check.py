"""Projection + actual raw-body branch with small typed schema/buffer fixtures, no GPUI."""
import argparse,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('desktop',type=Path);p.add_argument('--rustc',default='rustc');a=p.parse_args();base=a.desktop/'src/ui/settings'
se=(base/'search.rs').read_text();sp=(base/'spot.rs').read_text();pr=(base/'params.rs').read_text()
def between(s,a,b):i=s.index(a);return s[i:s.index(b,i)]
def body(s,a):
 i=s.index(a);b=s.index('{',i);j=b+1;n=1
 while n:n+=(s[j]=='{')-(s[j]=='}');j+=1
 return s[i:j]
modern='fn params_json(' in sp
trans={'DEST':between(sp,'#[derive(Clone, Debug, PartialEq, Eq)]\npub(super) struct Destination','pub(super) struct Spot'),'FIELD':body(sp,'pub(super) fn field('),'RAW':body(sp,'pub(super) fn params_json(') if modern else '', 'FINDER':between(se,'const LIMIT:','/// Russian names').replace('pub(super)','pub(crate)'),'SCOPE':between(se,'struct Scope<','#[cfg(test)]\nmod tests').replace('crate::settings::section_scope','section_scope'), 'SEARCH':body(se,'fn search_params('),'RAWBODY':body(pr,'if self.is_json(slot, module) {').replace('super::spot::','spot::'),'PATCHED':str(modern).lower()}
code=Path(__file__).with_name('review.rs.in').read_text()
for name,s in trans.items():code=code.replace('/*'+name+'*/',s)
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'test.rs';out=p.with_suffix('');p.write_text(code);subprocess.run([a.rustc,'--edition=2024','-Awarnings',p,'-o',out],check=True);subprocess.run([out],check=True)
