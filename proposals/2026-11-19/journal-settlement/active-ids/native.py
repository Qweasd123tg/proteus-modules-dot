import json,sys,pathlib,subprocess,os
here=pathlib.Path(__file__).resolve().parent; root=here.parent; source=root/'perf-r7-core-design'; deps=root/'perf-round2-core/target-release/release'; rust='/tmp/proteus-toolchain/local/bin/rustc'
src=source/'crates/proteus-session-semantics'; base=here/'baseline'
if not base.exists():
    base.mkdir(); subprocess.run(f'git -C {source} archive HEAD crates/proteus-session-semantics | tar -x -C {base}',shell=True,check=True)
def externs(name):
    fp=deps/'.fingerprint'; f=next(fp.glob(f'{name.replace("_","-")}-*/lib-{name}.json')); spec=json.loads(f.read_bytes()); args=[]; files={}
    for _,n,_,key in spec['deps']:
        matches=[p for p in (deps/'deps').glob(f'lib{n}-*.rlib') if any(ff.read_text()==key.to_bytes(8,'little').hex() for ff in fp.glob(f'*-{p.stem.split("-")[-1]}/lib-{n}'))]
        if not matches: matches=[p for p in (deps/'deps').glob(f'lib{n}-*.so')]
        assert len(matches)==1,(n,matches)
        args+=['--extern',f'{n}={matches[0]}']; files[n]=matches[0]
    return args,files
common=[rust,'--edition=2024','-C','opt-level=3','-C','debuginfo=0','-C','codegen-units=16','-L',f'dependency={deps/"deps"}','-L',f'native={deps}/build/ring-77831097f98a8255/out']
if __name__ != '__main__':
  modes=[]
else:
  modes=[('base',base/'crates/proteus-session-semantics'),('after',src)]
for mode,crate in modes:
    args,files=externs('proteus_session_semantics')
    lib=here/mode/'libproteus_session_semantics.rlib'; lib.parent.mkdir(exist_ok=True)
    subprocess.run(common+['--crate-type=rlib','--crate-name','proteus_session_semantics',str(crate/'src/lib.rs'),*args,'-o',str(lib)],check=True)
    pdeps=['--extern',f'proteus_contracts={files["proteus_contracts"]}','--extern',f'proteus_session_semantics={lib}']
    for suf,flags in [('',[]),('-alloc',['--cfg','count_allocs'])]:
        subprocess.run(common+[str(here/'probe.rs'),*pdeps,*flags,'-o',str(here/mode/('probe'+suf))],check=True)
