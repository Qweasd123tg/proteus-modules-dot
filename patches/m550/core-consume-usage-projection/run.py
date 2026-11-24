"""Exact native M362 Semantics with checked native lifted Core callers.
I/O boundary substitute only: owned typed records, CompareSnapshots result, display trace.
"""
from stage import D,R,staged,sha,git,SIDES
from pathlib import Path
import subprocess,json,tarfile,tomllib,sys,os
src,actual=staged(); W=D/'m362'; L=D/'proof-logs'; L.mkdir()
witness=json.loads((D/'source-stage.json').read_text())
assert witness['source_patch_sha']==sha((D/'source.patch').read_bytes())
p='crates/proteus-core/src/core/session_store/remote/snapshot.rs'
def lift(b,alias):
 s=b.decode()
 start=s.index('    fn validate_snapshot(');end=s.index('    pub(crate) fn cursor(&self)',start)
 return s[start:end].replace('    fn validate_snapshot(',f'    fn {alias}(',1)
before=lift(src[p][1],'validate_before');new=lift((W/p).read_bytes(),'validate_after')
assert before.replace('validate_before(','validate_after(',1).replace('usage.snapshot(','usage.into_snapshot(',1)==new
routes=b'impl RemoteValidatedRead {\n'+before.encode()+new.encode()+b'}\n'
sem=W/'crates/proteus-session-semantics'
(sem/'routes.rs').write_bytes(routes)
w=sem/'src/journal/usage.rs'
new_b=(D/'proof.rs').read_bytes().replace(b'"/../../routes.rs"',b'"/routes.rs"')
(w.parent/'usage_m362_proof.rs').write_bytes(new_b)
for name,(mode,b) in src.items():
 found=(W/name).read_bytes()
 if name in actual: assert git(found)==actual[name]['new_blob']
 else: assert found==b
w.write_bytes(w.read_bytes()+b'\n#[cfg(test)]\n#[path="usage_m362_proof.rs"]\nmod m362_proof;\n')
T=R/'toolchains/rust/rustup/toolchains/1.95.0-x86_64-unknown-linux-gnu/bin'; V=R/'r280/deps/vendor'
lock=(R/'m350/session-tests/planning/Cargo.lock').read_bytes()
orig={(p['name'],p['version']):p for p in tomllib.loads(src['Cargo.lock'][1].decode())['package']}
for p in tomllib.loads(lock.decode())['package']:
 q=orig[p['name'],p['version']]
 assert (p.get('checksum'),p.get('source'))==(q.get('checksum'),q.get('source'))
 if p.get('checksum'):assert json.loads((V/f"{p['name']}-{p['version']}"/'.cargo-checksum.json').read_bytes())['package']==p['checksum']
(W/'Cargo.lock').write_bytes(lock)
(W/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["crates/proteus-session-semantics"]\nexclude=["crates/proteus-contracts"]\n')
C=D/'cargo';C.mkdir()
B=Path('/tmp/m550-composed-core-target')
args=[str(T/'cargo'),'--offline','--locked','--config','source.crates-io.replace-with="exact"','--config','source.exact.directory='+json.dumps(str(V))]
env={'PATH':str(T)+':/usr/bin:/bin','HOME':str(C),'CARGO_HOME':str(C),'CARGO_TARGET_DIR':str(B),'RUSTC':str(T/'rustc'),'CARGO_INCREMENTAL':'0','CARGO_PROFILE_TEST_DEBUG':'0','LC_ALL':'C.UTF-8'}
results={}
for mode,opts in [('default',[]),('preserve_order',['--features','serde_json/preserve_order'])]:
 build=L/(mode+'-compile.jsonl')
 with build.open('wb') as out,(L/(mode+'-compile.txt')).open('wb') as err:
  subprocess.run(args+['test','--lib','--no-run','--message-format=json','-j1',*opts],cwd=W,env=env,stdout=out,stderr=err,check=True)
 rows=[json.loads(x) for x in build.read_bytes().splitlines()]
 root,=[x for x in rows if x.get('executable') and x['target']['name']=='proteus_session_semantics']
 contracts,=[x for x in rows if x.get('reason')=='compiler-artifact' and x['target']['name']=='proteus_contracts']
 tm,=[x for x in rows if x.get('reason')=='compiler-artifact' and x['target']['name']=='serde_json']
 assert not root['fresh'] and contracts['target']['src_path']==str(W/'crates/proteus-contracts/src/lib.rs')
 if contracts['fresh']:
  # The correct full dependency was successfully compiled in the discarded
  # sidecar-name-error attempt. Explicit identity check defeats donor cache reuse.
  previous=D/'failed-proof-syntax/proof-logs'/f'{mode}-compile.jsonl'
  prior=[json.loads(x) for x in previous.read_text().splitlines()]
  c,=[x for x in prior if x.get('reason')=='compiler-artifact' and x['target']['name']=='proteus_contracts']
  assert not c['fresh'] and c['target']['src_path']==contracts['target']['src_path']
  assert c['filenames']==contracts['filenames'] and c['features']==contracts['features']
  for f in c['filenames']:
   assert Path(f).stat().st_mtime_ns<=previous.stat().st_mtime_ns

 assert ('preserve_order' in tm['features'])==(mode=='preserve_order')
 binary=Path(root['executable']); assert binary.is_relative_to(B)
 log=L/(mode+'-tests.txt')
 with log.open('wb') as o:
  subprocess.run([binary,'--test-threads=1','--nocapture'],cwd=W,env=env,stdout=o,stderr=o,check=True)
 raw=log.read_text()
 assert '21 passed; 0 failed; 0 ignored' in raw,raw[-400:]
 assert raw.count('OWNERS ')==27
 results[mode]=dict(tests=21,ownership_controls=27,test_log_sha256=sha(log.read_bytes()),executable_sha256=sha(binary.read_bytes()),serde_features=tm['features'])
 print(mode,results[mode],flush=True)
(D/'native-receipt.json').write_text(json.dumps(dict(source=witness,act='native bundled Semantics + 2 test-only proofs; exact selected Core fold with typed portable boundary stand-ins',scope='no native AppServer, no memory/timing measure',proof_sha256=sha((D/'proof.rs').read_bytes()),route_sha256=sha(routes),results=results),indent=2)+'\n')
