"""Source-linked, pure fixture. Usage: replay.py CORE_SOURCE_OR_BEFORE PATCH SERDE_RLIB SERDE_JSON_RLIB [RUSTC]. No full CLI/runtime."""
from pathlib import Path
import sys,subprocess,hashlib,tempfile,shutil,re
root,pch,serde,json=map(lambda s: Path(s).resolve(),sys.argv[1:5]);rust=sys.argv[5] if len(sys.argv)>5 else 'rustc'
assert hashlib.sha256(pch.read_bytes()).hexdigest()=='bc6f2306ab783d01227a87c0cf971c3182f9d7622731de9fe1e580763ce2746d'
modroot=Path('crates/proteus-core/src/core/topology_render')
def blob(p):
    b=p.read_bytes();return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
full=(root/modroot).is_dir(); files=['map','markdown','table','helpers']
def file(name):
    return root/(modroot/f'{name}.rs' if full else f'{name}.rs')
for name,sha in zip(files,['18fc89dc63a826cf332e5cd9be50a10a35b6b1ba','0df6e8c9097f7ee2a85d14018e0cd5ffaba81e85','3546896459ed0bece8bf1cdef9bdef3521126acf','f7fa50d31165177c9e96a454000090a5aff4ff1e']):assert blob(file(name))==sha,name
if full:
    schema=(root/'crates/proteus-contracts/src/app_protocol/topology.rs').read_text();i=schema.index('pub struct SlotTopology');a=schema.rindex('#[derive',0,i);slot=schema[a:schema.index('\n}',i)+2]
else:slot=(root/'slot.rs').read_text()
frame=Path(__file__).with_name('frame.rs.in').read_text()
with tempfile.TemporaryDirectory() as td:
    tmp=Path(td);target=tmp/modroot;target.mkdir(parents=True)
    for f in files:shutil.copyfile(file(f),target/(f+'.rs'))
    shutil.copyfile(root/(modroot.with_suffix('.rs') if full else 'topology_render.rs'),target.with_suffix('.rs'))
    subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(pch)],cwd=tmp,check=True,stdout=subprocess.DEVNULL)
    res=[]
    for variant in ['before','after']:
        src=frame.replace('@@slot@@',slot).replace('@@regression@@',(target/'slot_order_tests.rs').read_text())
        for f in files:src=src.replace('@@'+f+'@@',(file(f) if variant=='before' else target/(f+'.rs')).read_text())
        unit=tmp/'probe.rs';unit.write_text(src)
        flags=[rust,'--edition=2024','-Awarnings','-O',str(unit),'--extern','serde='+str(serde),'--extern','serde_json='+str(json),'-L','dependency='+str(serde.parent),'-L','dependency='+str(json.parent)]
        subprocess.run(flags+['--test','-o',str(tmp/'test')],check=True)
        t=subprocess.run([str(tmp/'test')],capture_output=True,text=True)
        assert (t.returncode==0)==(variant=='after'),t.stdout
        if variant=='before':assert 'assertion `left == right` failed' in t.stdout
        subprocess.run(flags+['-o',str(tmp/'gate')],check=True)
        out=subprocess.check_output([str(tmp/'gate'),variant],text=True)
        print(variant, 'same in-tree regression: '+('green' if t.returncode==0 else 'red on row order'));print(out,end='')
        res.append(re.search(r'content=(\d+) canonical_wire=(\d+)',out).groups())
    assert res[0]==res[1],res
    print('Row-order-independent full-report contents and all canonically ordered wire cases are identical across versions.')
