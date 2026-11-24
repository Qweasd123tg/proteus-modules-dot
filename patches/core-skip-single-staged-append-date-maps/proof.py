#!/usr/bin/env python3
"""Replay the isolated R269 single staged record date patch with only pinned offline inputs."""
import argparse
import hashlib
from itertools import permutations
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT_BLOB = "5ccb49807bba4a46220d589b3748a393aab7258e"
CORE_COMMIT = "b2d2e6dedf0ea423b5f149c12ef98b8a0de01b14"
TOOL_PINS = {
    "cargo": "841072d1d92f9e841d9ba5b0814182a0adf064acf4527cd120967b7bc49dcb66",
    "rustc": "bff349e72704ff70bc08a234a3847338e797065bbedde5e556808bc87b7bf7c6",
    "rustfmt": "56b31ad3ec8fe0277a2884a189e243b8f04e9b48e5fd22e547c1516c5f8fd34c",
}
def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def identity(path):
    data = path.read_bytes()
    git_blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    return {"bytes": len(data), "sha256": sha(data), "git_blob": git_blob}

def vendorize(repo_lock, proof_lock, dirs, dest):
    original = {(p["name"], p["version"]):p for p in tomllib.loads(repo_lock)["package"] if "checksum" in p}
    dest.mkdir()
    packages = [p for p in tomllib.loads(proof_lock)["package"] if "checksum" in p]
    need(len(packages) == ARCHIVE_COUNT, "exact proof archive closure")
    for pkg in packages:
        key = pkg["name"], pkg["version"]
        name = "-".join(key)
        archive = next((p/(name+".crate") for p in dirs if (p/(name+".crate")).is_file()), None)
        pinned = original.get(key, {})
        need(archive and pinned.get("source") == pkg["source"] and pinned.get("checksum") == pkg["checksum"] == sha(archive.read_bytes()), f"official Core package {name}")
        need(pkg["source"] == "registry+https://github.com/rust-lang/crates.io-index", f"registry identity {name}")
        root = dest/name
        root.mkdir()
        sums = {}
        with tarfile.open(archive, "r:gz") as tar:
            for entry in tar:
                full = Path(entry.name)
                need(not full.is_absolute() and full.parts[0] == name and ".." not in full.parts, f"safe archive path for {name}")
                if entry.isdir():
                    continue
                need(entry.isfile() and len(full.parts)>1, f"regular package file {name}")
                rel = Path(*full.parts[1:]); x = rel.as_posix()
                need(x not in sums and x != ".cargo-checksum.json", f"unique file {name}/{x}")
                p = root/rel; p.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(entry).read()
                p.write_bytes(data)
                if entry.mode & 0o100:
                    p.chmod(0o755)
                sums[x] = sha(data)
        (root/".cargo-checksum.json").write_text(json.dumps({"package": pkg["checksum"], "files": sums}, sort_keys=True))



ARCHIVE_COUNT = 47
CORE = 'crates/proteus-core/src/'
TRANSCRIPT = CORE + 'app_server/transcript.rs'
JOURNAL = CORE + 'app_server/transcript/journal.rs'
SOURCE = CORE + 'app_server/transcript/journal/source.rs'
TIMESTAMPS = CORE + 'app_server/transcript/journal/timestamps.rs'
STAGED_TEST = CORE + 'app_server/transcript/journal/source/tests/staged_text.rs'
SNAPSHOT = CORE + 'core/session_store/remote/snapshot.rs'
STAGE = CORE + 'core/session_store/remote/snapshot/display_records.rs'
PATCH_NAMES = {'567':'composition-567.patch','569':'composition-569.patch','r269':'source.patch'}
PATCH_PATHS = {'567':{STAGE}, '569':{TRANSCRIPT,JOURNAL,SOURCE},
               'r269':{SNAPSHOT,STAGE,SOURCE,TIMESTAMPS,STAGED_TEST}}
PATCH_IDS = tuple(PATCH_NAMES)
PATHS = sorted(set().union(*PATCH_PATHS.values()))
PREDECESSORS = {
    '567': {
        'head_sha':'1b8b37fc4a622d6df32880e44cca64c2df89b3d7',
        'git_blob':'00aeba5963fd41e6e144abbcdcb456a5a979f930',
        'sha256':'0a6458e64f8a2c06f06e5471b648ddad56fa9f1927d74151f463f80a7c08443d',
        'postimages':{STAGE:'33ae48e97c72b335242385cf7dba2dbd6a90c02d'},
    },
    '569': {
        'head_sha':'9d015bae8dc44b42a5dfc1e1418e83d0ef1dba3b',
        'git_blob':'39a2b864d4100eea384b25baeedeeb30b99c6d28',
        'sha256':'72355dacb22f246307e3b48ab960fee01b640c72d00e3d641f855b84b8bdad23',
        'postimages':{
            TRANSCRIPT:'8f620eb244563e30b3a5f8f9a31bda68608d37bd',
            JOURNAL:'5ad34c82140b9db4a542c9992cacb2cbe5c7b153',
            SOURCE:'3c904ab22466f78ecc76e9546377e93f96e54635',
        },
    },
}
DESKTOP_ANCHOR = {
    'repository':'Proteus-harness/Proteus-desktop',
    'commit':'f8cc40177ad3ab3d8ec36447a899332778f03268',
    'path':'examples/performance/native-history/run.py',
    'git_blob':'eac7fbbb77f7acea61e1ca1014ab2c2c12d349bd',
}

def compile_inputs(src, packet, w, run, expect=None, stock_inputs=None):
    """Check all six textual orders, all eight subsets, and every reverse step."""
    def populate(p, source_path, paths):
        for f in paths:
            (p/f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path/f,p/f)
    def snapshot(p):
        tracked=sorted(f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file())
        need(tracked==PATHS,'exact patch scope after step')
        return {f:identity(p/f)['git_blob'] for f in PATHS}
    def apply(p,name,reverse=False):
        cmd=['git','apply','--whitespace=error-all'] + (['--reverse'] if reverse else [])
        patch=packet/PATCH_NAMES[name]
        stats=run(cmd+['--numstat',patch],p,True).splitlines()
        need(len(stats)==len(PATCH_PATHS[name]) and {s.split('\t',2)[2] for s in stats}==PATCH_PATHS[name],
             'unexpected patch scope: '+name)
        run(cmd+['--check',patch],p)
        run(cmd+[patch],p)
    def freeze(seen,p,added):
        key='+'.join(sorted(added)) or 'stock'
        cur=snapshot(p)
        if expect is not None:
            need(cur==expect[key],'declared composition blob mismatch: '+key)
        need(cur==seen.setdefault(key,cur),'noncommuting patches: '+key)
    for n, meta in PREDECESSORS.items():
        got=identity(packet/PATCH_NAMES[n])
        need(got['git_blob']==meta['git_blob'] and got['sha256']==meta['sha256'], 'published #'+n)
    seen={}
    for i,order in enumerate(permutations(PATCH_IDS)):
        tree=w/f'order-{i}';populate(tree,src,PATHS)
        applied=[];freeze(seen,tree,applied)
        for n in order:
            apply(tree,n);applied.append(n);freeze(seen,tree,applied)
        while applied:
            apply(tree,applied.pop(),True);freeze(seen,tree,applied)
    need(len(seen)==8,'all eight possible patch subsets')
    for n, meta in PREDECESSORS.items():
        need(all(seen[n][p]==b for p,b in meta['postimages'].items()), 'published postimages #'+n)
    for folder,names in [('changed',('r269',)),('composition_base',('567','569')),('composition',PATCH_IDS)]:
        tree=w/(folder+'-delta');populate(tree,src,PATHS)
        for n in names:
            apply(tree,n)
        freeze(seen,tree,names)
        full=w/folder
        populate(full,src,stock_inputs if stock_inputs is not None else PATHS)
        populate(full,tree,PATHS)
    return seen

def main():
    from lift import SOURCES, generate

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--archives', type=Path, action='append', required=True)
    p.add_argument('--desktop-source', type=Path, help='optional pin check; network and desktop execution are never used')
    p.add_argument('--cpu', type=int, help='optional Linux CPU number used for the release CPU probes')
    a = p.parse_args()
    src = a.source.resolve(strict=True)
    tool = a.toolchain_bin.resolve(strict=True)
    ars = [d.resolve(strict=True) for d in a.archives]
    work = a.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    need(not (work/'verification.json').exists(), "use a fresh work path; an existing verification.json is never silently reused")
    meta = json.loads((HERE/'SOURCE-PROVENANCE.json').read_text())
    need(meta["commit"] == CORE_COMMIT and meta["repository"] == "Proteus-harness/Proteus-core", "upstream identity")
    need(meta["source_inputs"]["Cargo.lock"] == ROOT_BLOB, "pinned upstream lock")
    need(len(meta['source_inputs']) == 42 and set(SOURCES) == set(meta['source_inputs']) and
         set(PATHS) <= set(meta['source_inputs']), 'exact recorded source closure')
    for f, blob in meta['source_inputs'].items():
        need(identity(src/f)['git_blob'] == blob, "official source: " + f)
    for f, pin in TOOL_PINS.items():
        need(pin == sha((tool/f).read_bytes()) == meta['toolchain_sha256'][f], "toolchain hash: " + f)
    need(meta['production_changes'] == sorted(PATCH_PATHS['r269']), 'R269 patch scope')
    need(meta['composition_inputs'] == PREDECESSORS, 'exact published composition pins')
    need(meta['desktop_anchor'] == DESKTOP_ANCHOR, 'public benchmark source pin')
    if a.desktop_source:
        need(identity(a.desktop_source/DESKTOP_ANCHOR['path'])['git_blob'] == DESKTOP_ANCHOR['git_blob'],
             'native-history configuration anchor')
    for f in ['Cargo.toml', 'Cargo.lock', 'source.patch']:
        need(sha((HERE/f).read_bytes()) == meta["packet_sha256"][f], "packet digest: " + f)
    with tempfile.TemporaryDirectory(dir=work, prefix='r269-') as temporary:
        w = Path(temporary)
        env = {
            'PATH': str(tool) + ':/usr/bin:/bin', 'HOME': temporary, 'RUSTC': str(tool/'rustc'),
            'CARGO_HOME': str(w/'cargo-home'), 'CARGO_TARGET_DIR': str(w/'target'),
            'TMPDIR': temporary, 'R269_TMP': temporary, 'R260_TMP': temporary, 'LC_ALL': 'C.UTF-8', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CEILING_DIRECTORIES': temporary,
        }
        def run(argv, cwd=None, capture=False):
            return subprocess.run(argv, cwd=cwd or w, env=env, check=True, timeout=600,
                                  stdout=subprocess.PIPE if capture else None, text=True).stdout
        matrix=compile_inputs(src,HERE,w,run,meta['composition_blobs'],meta['source_inputs'])
        changed=w/'changed';composed=w/'composition'
        for root,paths in [(changed,PATCH_PATHS['r269']),(composed,PATHS)]:
            run([tool/'rustfmt','--edition','2024','--config','skip_children=true','--check',
                 *(root/f for f in sorted(paths))])
        vendorize((src/'Cargo.lock').read_text(), (HERE/'Cargo.lock').read_text(), ars, w/'vendor')
        crate = w/'crate'
        crate.mkdir()
        for f in ('Cargo.lock', 'Cargo.toml'):
            shutil.copyfile(HERE/f, crate/f)
        generate(src, changed, crate/'src', composed)
        generated=crate/'src'
        needles=('self.uniform_message_date = Some(at.timestamp_ms);',
                 'if line.capacity() > MAX_RETAINED_FINAL_SCAN_BYTES',
                 'fn append_staged_message(')
        for arm, expected in {
            'stock':(False,False,False), 'candidate':(True,False,False),
            'baseline':(False,True,True), 'composed':(True,True,True),
        }.items():
            paths=list((generated/arm).rglob('*.rs'))+list(generated.glob(arm+'.rs'))
            code='\n'.join(p.read_text() for p in paths)
            need(bool(paths) and tuple(needle in code for needle in needles)==expected,
                 'wrong R269/#567/#569 implementation mix in generated arm: '+arm)
        cargo = [tool/'cargo', '--offline', '--locked', '--config',
                 'source.crates-io.replace-with="verified"', '--config',
                 'source.verified.directory=' + json.dumps(str(w/'vendor'))]
        records = {}
        cpu_binaries = {}
        for mode in ('default', 'preserve_order'):
            flags = ['--features', 'meter' if mode == 'default' else 'meter,preserve_order']
            graph = run(cargo + ['tree', '-e', 'features'] + flags, crate, True)
            for node in ['ring v0.17.14', 'serde_json v1.0.151', 'serde v1.0.228', 'tempfile v3.27.0']:
                need(node in graph, "authentic feature graph: "+node)
            inverse = run(cargo + ['tree', '-e', 'features', '-i', 'serde_json'] + flags, crate, True)
            need(('serde_json feature "preserve_order"' in inverse) == (mode == 'preserve_order'), "serde map mode")
            records[mode] = {}
            for profile in ('release', 'debug'):
                run(cargo + ['build'] + (['--release'] if profile == 'release' else []) + flags, crate)
                exe = w/'target'/profile/'r269-staged-date-proof'
                semantics = run([exe, 'semantics'], capture=True)
                print(f"{mode} {profile}:\n{semantics}", flush=True)
                need('SEMANTICS PASS' in semantics.splitlines(), "missing complete semantic receipt")
                records[mode][profile] = {'semantics': semantics}
                allocation=run([exe,'allocation'],capture=True)
                print(allocation,flush=True)
                need('ALLOCATION PASS' in allocation.splitlines(), 'missing scoped allocation receipt')
                records[mode][profile]['allocation']=allocation
                if profile == 'release':
                    cpu_bin=w/('r269-cpu-'+mode)
                    shutil.copyfile(exe,cpu_bin)
                    cpu_bin.chmod(0o755)
                    cpu_binaries[mode]=cpu_bin
            need(records[mode]['release']['semantics'] == records[mode]['debug']['semantics'],
                 'within-mode debug/release semantic mismatch')
        # All compilation and parity checks precede timing; completed binaries run serially.
        for mode, exe in cpu_binaries.items():
            if a.cpu is None:
                cpu=run([exe,'cpu'],capture=True)
            else:
                saved=os.sched_getaffinity(0)
                try:
                    os.sched_setaffinity(0,{a.cpu})
                    cpu=run([exe,'cpu'],capture=True)
                finally:
                    os.sched_setaffinity(0,saved)
            need('CPU PASS' in cpu.splitlines(),'scoped timing guard did not pass')
            records[mode]['release']['cpu']=cpu
            print(mode, cpu,flush=True)
        receipt = {
            'run': 'PASS', 'scope': 'isolated exact-source stage/renderer; no full workspace build, process RSS/PSS, or app startup timing',
            'repository': meta['repository'], 'commit': CORE_COMMIT, 'changed_paths': sorted(PATCH_PATHS['r269']),
            'standalone_postimages': matrix['r269'],
            'checked_source_blobs': meta['source_inputs'], 'toolchain_sha256': TOOL_PINS,
            'composition_blobs': matrix, 'apply_and_reverse_permutations': 6,
            'composition_inputs': meta['composition_inputs'],
            'package_archive_count': ARCHIVE_COUNT, 'offline_locked': True,
            'package_closure': sha((HERE/'Cargo.lock').read_bytes()), 'map_modes': records,
        }
        out = work/'verification.json'
        with out.open('x') as sink:
            json.dump(receipt, sink, indent=2)
            sink.write('\n')
        print('Verified six patch orderings and exact reverse, both profiles and map layouts, and recorded scoped CPU observations.', flush=True)

if __name__ == '__main__':
    main()
