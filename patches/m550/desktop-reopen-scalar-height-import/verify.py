#!/usr/bin/env python3
"""Replay exact M401 geometry import stock and candidate with a locked offline vendor."""
import argparse,base64,gzip,hashlib,json,os,re,shutil,subprocess,tempfile,tomllib
from pathlib import Path

P=Path(__file__).resolve().parent
SLOT=Path('src/ui/chat/scroller/scrollbar')
def sha(b):return hashlib.sha256(b).hexdigest()
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\x00'+b).hexdigest()
def read(p):return json.loads(p.read_bytes())

def manifest():
    for line in (P/'SHA256SUMS').read_text().splitlines():
        digest, name=line.split(None,1)
        assert sha((P/name).read_bytes())==digest,name

def rows(output):
    data={};tests=re.search(r'test result: ok\. (\d+) passed; 0 failed',output)
    assert tests,output
    names=('requests','gross_bytes','net_bytes','peak_delta_bytes','largest_request',
           'accepted','loaded_prefix','span_count','revision','logical_charge','geometry_sha256')
    for line in output.splitlines():
        if 'M401_GEOMETRY ' in line:
            k,*v=line.split('M401_GEOMETRY ',1)[-1].split()
            assert k not in data and len(v)==len(names),line
            data[k]=dict(zip(names,[*map(int,v[:5]),v[5]=='true',*map(int,v[6:10]),v[10]],strict=True))
    return {'tests':int(tests.group(1)),'cases':data}

def verify_vendor(vendor):
    pins=read(P/'native-pins.json')['lock_packages']
    for package in tomllib.loads((P/'Cargo.lock').read_text())['package']:
        if 'checksum' not in package:
            assert package['name']=='m401-geometry-replay'
            continue
        n=package['name']+'-'+package['version']
        assert pins[n]==package['checksum'],n
        meta=read(vendor/n/'.cargo-checksum.json')
        assert meta['package']==pins[n],n
        for path,digest in meta['files'].items():
            assert sha((vendor/n/path).read_bytes())==digest,(n,path)

def run(vendor,keep):
    manifest()
    verify_vendor(vendor)
    expected=read(P/'receipt.json')
    pin=read(P/'composition.json')
    covered=sorted(P.glob('sources-*.gz.b64'))
    packed=gzip.decompress(base64.b64decode(''.join(q.read_text().strip() for q in covered),validate=True))
    assert sha(packed)==pin['packed_stock_json_sha256']
    stock={name:base64.b64decode(b,validate=True) for name,b in json.loads(packed)}
    check={q['path']:q['before'] for q in pin['authenticated_stock_leaves']}
    assert {n:oid(b) for n,b in stock.items()}==check
    rustc=subprocess.check_output(['rustc','--version'],text=True).strip()
    assert rustc == expected['rustc'],(rustc,expected['rustc'])
    target=Path(os.environ.get('CARGO_TARGET_DIR',keep/'target')).resolve()
    out={}
    for arm in ('stock','candidate'):
        root=keep/arm
        root.mkdir()
        for n,b in stock.items():
            f=root/n
            f.parent.mkdir(parents=True,exist_ok=True)
            f.write_bytes(b)
        if arm=='candidate':
            cmd=['git','apply','--whitespace=error','-p1',str(P/'source.patch')]
            subprocess.run([*cmd[:2],'--check',*cmd[2:]],cwd=root,check=True)
            subprocess.run(cmd,cwd=root,check=True)
            after={q['path']:q['after'] for q in pin['patched_leaves']}
            assert all(oid((root/n).read_bytes())==h for n,h in after.items())
            subprocess.run([*cmd[:2],'-R',*cmd[2:]],cwd=root,check=True)
            assert all((root/n).read_bytes()==v for n,v in stock.items())
            subprocess.run(cmd,cwd=root,check=True)
        # Preserve all production source bytes in the compiled modules. The
        # external test-only child declaration is the only harness injection.
        f=root/SLOT/'height_store.rs'
        assert f.read_bytes()==stock[str(SLOT/'height_store.rs')]
        with f.open('ab') as a:a.write(b'\n#[cfg(test)]\n#[path = "height_store/replay.rs"]\nmod m401_replay;\n')
        shutil.copyfile(P/'replay.rs',root/SLOT/'height_store/replay.rs')
        shutil.copyfile(P/'harness.rs',root/'src/lib.rs')
        shutil.copyfile(P/'meter.rs',root/'src/meter.rs')
        for name in ('Cargo.toml','Cargo.lock'):
            b=(P/name).read_bytes().replace(b'm401-geometry-replay',f'm401-geometry-{arm}'.encode())
            (root/name).write_bytes(b)
        d=root/'.cargo';d.mkdir()
        (d/'config.toml').write_text('[source.crates-io]\nreplace-with="vendor"\n[source.vendor]\ndirectory='+json.dumps(str(vendor))+'\n')
        cache=root/'cache';config=root/'config'
        cache.mkdir();config.mkdir()
        env=dict(os.environ,XDG_CACHE_HOME=str(cache),XDG_CONFIG_HOME=str(config),
                 CARGO_TARGET_DIR=str(target),CARGO_HOME=str(keep/'cargo-home'),CARGO_INCREMENTAL='0')
        p=subprocess.run(['cargo','test','--release','--locked','--offline','-j','2',
                          '--','--nocapture','--test-threads=1'],cwd=root,env=env,text=True,
                         stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (keep/(arm+'.log')).write_text(p.stdout)
        assert p.returncode==0,p.stdout
        out[arm]=rows(p.stdout)
        assert out[arm]==expected['arms'][arm],out[arm]
        print(arm,out[arm]['tests'],'tests')
    for k, a in out['stock']['cases'].items():
        b=out['candidate']['cases'][k]
        for prop in ('net_bytes','accepted','loaded_prefix','span_count','revision','logical_charge','geometry_sha256'):
            assert a[prop]==b[prop],(k,prop)
        assert b['requests']<=a['requests'] and b['gross_bytes']<=a['gross_bytes']
        print(k,a['requests'],b['requests'],a['gross_bytes'],b['gross_bytes'],a['net_bytes'],b['net_bytes'],b['geometry_sha256'])
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--vendor',type=Path,required=True)
    p.add_argument('--keep',type=Path)
    args=p.parse_args()
    if args.keep:
        keep=args.keep.resolve()
        keep.mkdir(parents=True,exist_ok=True)
        run(args.vendor.resolve(),keep)
    else:
        with tempfile.TemporaryDirectory(prefix='m401-geometry-replay-') as tmp:
            run(args.vendor.resolve(),Path(tmp))
