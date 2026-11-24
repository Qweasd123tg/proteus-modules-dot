#!/usr/bin/env python3
"""Verify and replay the full native R274 session-storage crate, with offline locked sources."""
from itertools import permutations
from pathlib import Path
import argparse
import json
import re
import shutil
import subprocess
from native_inputs import HERE, TOOL_PINS, cargo, git_blob, need, sha, stage_native_inputs
from stage_tests import attach

SRC = 'storage/session-storage/src/'
COMPONENTS = {
    'r274': ('source.patch','fadf4a5955552382c8def044f18d54482181a0b1',{
        SRC+'service/views.rs': ('cd578af057e066e4e1620d2f014ebc52fdaa934c','4e91d5fd6badfc7377a6d5ad3fff6b14127cb0fa'),
        SRC+'snapshot.rs': ('ecf417d4ebc712d2c5f724ced3fb676363f39fa6','6f42ed3b0ac96b47df314f5e42736e4433480a6d'),
    }),
    '579': ('composition-579.patch','640e5156971402ef9d3912ce16b163ab1bff898c',{
        SRC+'service/cache.rs': ('ca6c9629cf772ab9f0f0dcf3fa6a881777b582d1','562b0097590b33c76ee8cb20a1b4ea8eb310b6fa'),
    }),
    '581': ('composition-581.patch','3d799220056c380a1f70c07f1a065a5ab9d4e369',{
        SRC+'blob_codec.rs': ('2fbce7e2a00219068b59126a4348f424b8e651fc','6b08c343611167ae60a6f8d917a75a1ce3ad3587'),
    }),
}
def git_apply(work, root, n, reverse=False):
    filename, pin, scope = COMPONENTS[n]
    patch=HERE/filename
    need(git_blob(patch.read_bytes())==pin, f'exact source patch {n}')
    env={'PATH':'/usr/bin:/bin','HOME':str(work/'cargo-home'),'LC_ALL':'C.UTF-8',
         'GIT_CONFIG_GLOBAL':'/dev/null','GIT_CONFIG_NOSYSTEM':'1','GIT_CEILING_DIRECTORIES':str(work)}
    cmd=['git','apply','--whitespace=error-all']+(['--reverse'] if reverse else [])
    def run(extra, capture=False):
        return subprocess.run(cmd+extra+[patch], cwd=root, env=env,text=True,check=True,
                              stdout=subprocess.PIPE if capture else None,timeout=30).stdout
    paths={l.split('\t')[2] for l in run(['--numstat'],True).splitlines()}
    need(paths==set(scope),f'exact patch scope {n}')
    for path, (prior,post) in scope.items():
        need(git_blob((root/path).read_bytes())==(post if reverse else prior),f'validated preimage {path}')
    run(['--check']);run([])
    for path, (prior,post) in scope.items():
        need(git_blob((root/path).read_bytes())==(prior if reverse else post),f'validated postimage {path}')

def compose(work, stock):
    paths = sorted({p for _,_,m in COMPONENTS.values() for p in m})
    states={}
    def record(root, active):
        files=sorted(f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file())
        need(files==paths,'composition only targets explicitly pinned files')
        label='+'.join(sorted(active)) or 'stock'
        hashes={p:git_blob((root/p).read_bytes()) for p in paths}
        need(states.setdefault(label,hashes)==hashes,f'order independence: {label}')
    for i, order in enumerate(permutations(COMPONENTS)):
        w=work/f'composition-{i}'
        for p in paths:
            (w/p).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(stock/p,w/p)
        active=[];record(w,active)
        for n in order:
            git_apply(work,w,n);active.append(n);record(w,active)
        while active:
            git_apply(work,w,active.pop(),True);record(w,active)
    need(len(states)==8,'every patch subset')
    return states

ALLOC=re.compile(r'R274_ALLOC (\w+) turns=(\d+) seed=(\d+) at_return=(\d+) peak=(\d+) requested=(\d+) allocs=(\d+) reallocs=(\d+) fingerprint_bytes=(\d+)')
def tested(bin_path, work, subset=None, pair=None, mode=None):
    env={'PATH':'/usr/bin:/bin','HOME':str(work/'cargo-home'),'TMPDIR':str(work/'tmp'),'LC_ALL':'C.UTF-8'}
    if pair is not None:
        env.update(R274_PAIR_DIR=str(pair),R274_PAIR_MODE=mode)
    args=[bin_path,'--nocapture','--test-threads=1']+([subset] if subset else [])
    res=subprocess.run(args,cwd=work,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
    print(res.stdout if res.returncode else '\n'.join(line for line in res.stdout.splitlines() if ('R274_' in line or 'test result:' in line)),flush=True)
    need(res.returncode==0,'native test executable')
    return res.stdout

def build(work, tools, arm, profile, features):
    args=['test','-p','session-storage','--no-run','--message-format=json']+features
    if profile=='release': args+=['--release']
    # Both workspaces intentionally keep the upstream package ID. In a shared
    # target Cargo can otherwise reuse the opposite arm's relative fingerprints.
    # Clear this package's generated files *in this proof's isolated target*
    # before each arm; frozen executables and dependency artifacts are retained.
    clean_profile=['--release'] if profile=='release' else []
    cargo(work,tools,arm,'clean','-p','session-storage',*clean_profile,capture=True)
    out=cargo(work,tools,arm,*args,capture=True)
    matches=[line for line in out.splitlines() if line.startswith('{')]
    artifacts=[o for o in map(json.loads,matches)
               if o.get('reason')=='compiler-artifact' and o['target']['name']=='session_storage'
               and o['profile']['test'] and o.get('executable')]
    need(len(artifacts)==1,'one native complete test binary')
    artifact=artifacts[0]
    manifest=work/'native'/arm/'storage/session-storage/Cargo.toml'
    need(not artifact['fresh'] and Path(artifact['manifest_path'])==manifest
         and Path(artifact['target']['src_path'])==manifest.parent/'src/lib.rs',
         f'newly compiled unit-test artifact from the exact {arm} source tree')
    dst=work/f'{arm}-{profile}-session-storage'
    shutil.copy2(artifact['executable'],dst)
    return dst

def invariants(a,b,profile):
    lines=lambda o:sorted(line.split('R274_SEMANTIC ',1)[1] for line in o.splitlines() if 'R274_SEMANTIC ' in line)
    need(len(lines(a))==8 and lines(a)==lines(b),'eight matching native result traces')
    outcomes=lambda o:next(line for line in o.splitlines() if line.startswith('test result:'))
    status = lambda o: re.match(r'test result: ok\. (\d+) passed; 0 failed; (\d+) ignored;',outcomes(o))
    x,y=status(a),status(b)
    need(x and y and x.groups()==y.groups(),'paired native test counts')
    need(int(x[1]) >= (100 if profile=='debug' else 7),'full debug and seven release native cases')
    return {'traces':lines(a),'passed':int(x[1]),'ignored':int(x[2])}

def allocation_pair(work, binaries, name):
    pair=work/('alloc-paired-'+name)
    pair.mkdir()
    selected='r274_native_profile'
    tested(binaries['stock'],work,selected,pair,'seed')
    records=[]
    for side in ('stock','candidate'):
        o=tested(binaries[side],work,selected,pair,side)
        d={}
        for t in ALLOC.findall(o):
            d[f'{t[0]}-{t[1]}']=dict(zip(('seed','at_return','peak','requested','allocs','reallocs','fingerprint_bytes'),map(int,t[2:])))
        need(set(d)=={'Jsonl-0','Jsonl-120','Sqlite-0','Sqlite-120'},'both backend allocation and untouched controls')
        records.append(d)
    r0,r1=records
    for k in ('Jsonl','Sqlite'):
        need(r0[k+'-0']==r1[k+'-0'],'exact text-only allocation control '+k)
        u,v=r0[k+'-120'],r1[k+'-120']
        need(u['seed']==v['seed'] and u['at_return']==v['at_return']
             and u['fingerprint_bytes']==v['fingerprint_bytes'],'live and source extent exact '+k)
        need(u['peak']>v['peak']+10_000 and u['requested']>v['requested']+100_000 and u['allocs']>v['allocs'],
             'positive peak and allocation traffic saving '+k)
    return {'stock':r0,'candidate':r1}

def pair_bytes(work, binaries, name):
    pair=work/('paired-'+name)
    pair.mkdir()
    filter='r274_native_byte_pair'
    tested(binaries['stock'],work,filter,pair,'seed')
    a=tested(binaries['stock'],work,filter,pair,'stock')
    b=tested(binaries['candidate'],work,filter,pair,'candidate')
    trace=lambda o: sorted(line.split('R274_PAIR ',1)[1] for line in o.splitlines() if 'R274_PAIR ' in line)
    need(trace(a)==trace(b) and len(trace(a))==2,'same pinned input extent and decode counts')
    hashes={}
    for flavor in ('jsonl','sqlite'):
        for category in ('response','catalog','cache'):
            left,right=(pair/f'{flavor}-{side}-{category}.bytes' for side in ('stock','candidate'))
            lb,rb=left.read_bytes(),right.read_bytes()
            need(lb==rb and len(lb)>10,f'exact {flavor} {category} bytes')
            hashes[f'{flavor}-{category}']={'bytes':len(lb),'sha256':sha(lb)}
    return {'traces':trace(a),'bytes':hashes}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--modules',type=Path,required=True)
    p.add_argument('--core',type=Path,required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--toolchain-bin',type=Path,required=True)
    p.add_argument('--archives',type=Path,action='append',required=True)
    args=p.parse_args()
    w,tool=args.work.resolve(),args.toolchain_bin.resolve()
    stock,candidate=stage_native_inputs(args.modules,args.core,w,tool,args.archives)
    matrix=compose(w,stock)
    git_apply(w,candidate,'r274')
    git_apply(w,candidate,'r274',True)
    git_apply(w,candidate,'r274')
    fmt=[tool/'rustfmt','--edition','2024','--config','skip_children=true','--check']
    subprocess.run(fmt+[candidate/path for path in COMPONENTS['r274'][2]]
                   +[HERE/'native.rs',HERE/'meter.rs'],check=True,timeout=15)
    for root in (stock,candidate): attach(root)
    records={mode:{profile: trial(w,tool,mode,profile) for profile in ('debug','release')}
             for mode in ('default','preserve_order')}
    seal_receipt(w,matrix,records)

def trial(w,tool,map_mode,profile):
    features=['--features','serde_json/preserve_order'] if map_mode!='default' else []
    graph=cargo(w,tool,'stock','tree','-p','session-storage','-e','features','-i','serde_json',*features,capture=True)
    need(('serde_json feature "preserve_order"' in graph)==bool(features),'native desired serde map mode')
    binaries={a:build(w,tool,a,profile,features) for a in ('stock','candidate')}
    hashes={a:sha(bin_path.read_bytes()) for a,bin_path in binaries.items()}
    need(len(set(hashes.values()))==2,'distinct freshly compiled stock/candidate executable bytes')
    subset='r274_native' if profile=='release' else None
    record=invariants(*(tested(exe,w,subset) for exe in binaries.values()),profile)
    record['fresh_distinct_test_artifact_sha256']=hashes
    record['same_seed_exact_bytes']=pair_bytes(w,binaries,map_mode+'-'+profile)
    record['same_seed_allocator']=allocation_pair(w,binaries,map_mode+'-'+profile)
    return record

def seal_receipt(w,matrix,records):
    result={'status':'PASS','scope':'native session-storage -> native JSONL and SQLite; no live worker/IPC or whole workspace',
            'modules_commit':'331cfc20bbaf821ab07de49868426da29ebdeb64','core_dependency_commit':'0c1b7572313230e5d123e95c722e1258a2e9ecd6',
            'source_inventory_sha256':sha((HERE/'source-files.json').read_bytes()),'lock_sha256':sha((HERE/'Cargo.lock').read_bytes()),
            'package_archives':157,'toolchain_sha256':TOOL_PINS,'product_and_composition':COMPONENTS,
            'compose_orders':6,'composition_source_only_blobs':matrix,'native':records}
    with (w/'verification.json').open('x') as sink:
        json.dump(result,sink,indent=2)
        sink.write('\n')
    print('R274 PASS: native locked JSONL and SQLite, both maps/profiles, exact pairing and allocation guards',flush=True)
if __name__=='__main__':
    main()
