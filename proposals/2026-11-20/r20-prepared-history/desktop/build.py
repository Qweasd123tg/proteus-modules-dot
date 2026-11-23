"""Build only the tiny loopback driver and actual Desktop Api. Reuse locked Cargo artifacts."""
import argparse,hashlib,json,os,pathlib,re,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('desktop',type=Path)
p.add_argument('desktop_target',type=Path,help='target with complete native unit-test dependency graph')
p.add_argument('--rustc',default='rustc')
a=p.parse_args()
here=Path(__file__).resolve().parent
out=here/'pinned'; out.mkdir(exist_ok=True)
desktop=a.desktop.resolve(); target=a.desktop_target.resolve()
rev='7ccb6c8634c40f450d83bb6e9eff891dc776ee6b'
def git(*args):return subprocess.check_output(['git','-C',desktop,*args])
def content(name):return git('show',rev+':'+name)
def h(b):return hashlib.sha256(b).hexdigest()
manifest={'desktop':rev,'core_contracts':'7cbc7206f03fac130d05bed2844de275476fedc8','module_sha256':{}}
tree=git('ls-tree','-r','--name-only',rev,'src/api','src/startup_trace.rs').decode().splitlines()
for rel in tree:
 file=out/rel; file.parent.mkdir(exist_ok=True,parents=True)
 b=content(rel); file.write_bytes(b); manifest['module_sha256'][rel]=h(b)
b=content('src/backend.rs'); const=re.findall(rb'^pub\(crate\) const READY_TIMEOUT: Duration = Duration::from_secs\([0-9]+\);$',b,re.M); assert len(const)==1
(out/'backend_constant.rs').write_bytes(b'use std::time::Duration;\n'+const[0]+b'\n')
assert git('rev-parse','HEAD:crates/client-common')==git('rev-parse',rev+':crates/client-common')
manifest['client_common_tree']=git('rev-parse',rev+':crates/client-common').decode().strip()
assert git('diff','--exit-code','HEAD','--','crates/client-common')==b''
assert content('Cargo.lock')==(desktop/'Cargo.lock').read_bytes()
manifest['lock_sha256']=h(content('Cargo.lock'))
fp=target/'debug/.fingerprint'; deps=target/'debug/deps'
base=json.loads(next(fp.glob('proteus-native-*/test-bin-proteus-native.json')).read_text())
want=set('ureq proteus_contracts proteus_client_common uuid base64 anyhow serde serde_json'.split())
flags=[]; found={}
for _,name,_,sig in base['deps']:
 if name not in want:continue
 matches=[f for f in fp.glob('*/lib-'+name) if bytes.fromhex(f.read_text().strip())==sig.to_bytes(8,'little')]
 assert len(matches)==1,(name,matches)
 suffix=matches[0].parent.name.rsplit('-',1)[-1]
 rlib=deps/f'lib{name}-{suffix}.rlib';assert rlib.is_file(),rlib
 found[name]=rlib.name; flags+=['--extern',f'{name}={rlib}']
assert set(found)==want
manifest['cached_rlibs']=found
manifest['rustc']=subprocess.check_output([a.rustc,'--version'],text=True).strip()
subprocess.run([a.rustc,'--edition=2024','-C','link-arg=-fuse-ld=lld','-C','strip=debuginfo','-L',f'dependency={deps}',*flags,here/'client.rs','-o',here/'client'],check=True)
manifest['artifact_sha256']=h((here/'client').read_bytes())
manifest['driver_sha256']=h((here/'client.rs').read_bytes())
(here/'build-identity.json').write_text(json.dumps(manifest,indent=2)+'\n')
