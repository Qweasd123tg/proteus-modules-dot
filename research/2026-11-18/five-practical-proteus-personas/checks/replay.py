"""Offline replay for two reader paths, SDK/UI projections and a separately compiled pure renderer. No app, host, model, installer or worker."""
from pathlib import Path
import argparse,os,subprocess as sp,sys,tempfile,hashlib,shutil
p=argparse.ArgumentParser(description=__doc__)
for k in ['desktop','extensions','deps','markdown-rlib','rustc','cargo']:p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--node',default='node');p.add_argument('--backend-sdk',type=Path,help='optional exact offline fallback SDK checkout at b2c285f, never runs the worker');a=p.parse_args();root=Path(__file__).resolve().parents[1];deps=a.deps.resolve();se,=deps.glob('libserde-*.rlib');sj,=deps.glob('libserde_json-*.rlib')
def gd(path):return sp.check_output(['git','-C',path,'rev-parse','--absolute-git-dir'],text=True).strip()
d=gd(a.desktop);e=gd(a.extensions);rust=a.rustc.resolve();m=a.markdown_rlib.resolve();env={**os.environ,'CARGO_NET_OFFLINE':'true','RUSTC':str(rust),'PATH':str(a.cargo.resolve().parent)+os.pathsep+os.environ['PATH']}
def py(script,*args):sp.run([sys.executable,root/script,*args],check=True,env=env)
def put(t,repo,commit,f):z=t/f;z.parent.mkdir(parents=True,exist_ok=True);z.write_bytes(sp.check_output(['git','--git-dir='+repo,'show',commit+':'+f]))
for l in (root/'SHA256SUMS').read_text().splitlines():
 h,n=l.split('  ',1);assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
py('user/catalog/probe.py',d,e,rust,m,m.parent)
py('user/catalog/mermaid/render.py',e,'--node',a.node)
py('user/visual/checks/replay.py',e,rust,deps,m)
with tempfile.TemporaryDirectory() as t:
 t=Path(t);D=t/'desktop';E=t/'extensions';u='sdk/src/ui.rs';w='src/declarative/widget.rs';control='src/declarative/control.rs'
 put(E,e,'ef064381d2194d95faef2b85f6cc3a1c34c6b975',u)
 for f in (w,control):put(D,d,'2307e9c67125bbe66f15ced51317a2dfcc437aa4',f)
 py('author/panel/checks/replay.py','--sdk-ui',E/u,'--widget',D/w,'--control',D/control,'--serde',se,'--serde-json',sj,'--rustc',rust)
 cmd=[a.cargo,'test','--locked','--offline','--manifest-path',root/'author/renderer/checks/logic/Cargo.toml','--target-dir',t/'logic-target','--lib']
 sp.run(cmd,check=True,env=env)
 py('author/renderer/checks/public_shapes.py',E,D)
 if a.backend_sdk:
  package=t/'word-count-fallback'
  py('author/backend/offline/prepare.py',a.backend_sdk,package)
  env2={**env,'CARGO_TARGET_DIR':str(t/'backend-target')}
  for args in [('build','--locked','--offline','--bin','proteus-word-count-example'),('test','--locked','--offline','--lib')]:
   sp.run([a.cargo,*args],cwd=package,env=env2,check=True)
  print('PASS: optional backend binary compiled using the documented alternative SDK; only library tests executed (no worker).')
 else:print('SKIPPED here: alternative backend SDK build (provide --backend-sdk). The separate recorded run is in author/backend/evidence.')
print('PASS: offline examples tested. No live Desktop, worker, model, host, account or install.')
