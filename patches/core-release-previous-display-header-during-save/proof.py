#!/usr/bin/env python3
"""Replay the isolated R267 cold-save previous-header patch with only pinned offline inputs."""
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
    need(len(packages) == 38, "exact proof archive closure")
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


VIEW = 'crates/proteus-core/src/core/session_store/remote/view.rs'
CACHE = 'crates/proteus-core/src/core/session_store/remote/view/cache.rs'
# These git blobs are the published source.patch files, not the PR diffs or
# the blobs of their target Rust modules.
COMPONENT_BLOBS = {
    '571': '51e87d7d3fbdb958d93dfd62bacbad03628ad518',
    '574': '8121303918e5336c1db6cd953dcb7143096ee057',
}
PATCH_PATHS = {'571': VIEW, '574': CACHE, 'r267': CACHE}
PATCH_NAMES = {'571': 'composition-571.patch', '574': 'composition-574.patch', 'r267': 'source.patch'}
PATCH_IDS = tuple(PATCH_PATHS)

def compile_inputs(src, packet, w, run, expect=None):
    """Check every application permutation, every intermediate pair, and full rollback."""
    def init(p):
        for f in (VIEW, CACHE):
            (p/f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src/f,p/f)
    def snapshot(p):
        tracked = sorted(f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file())
        need(tracked == sorted([VIEW,CACHE]), 'exact two-file composition scratch scope')
        return {f: identity(p/f)['git_blob'] for f in (VIEW,CACHE)}
    def apply(p, name, reverse=False):
        cmd=['git','apply','--whitespace=error-all'] + (['--reverse'] if reverse else [])
        patch=packet/PATCH_NAMES[name]
        stat=run(cmd+['--numstat',patch],p,True).splitlines()
        need(len(stat)==1 and stat[0].split('\t')[2]==PATCH_PATHS[name], 'unexpected patch scope: '+name)
        run(cmd+['--check',patch],p)
        run(cmd+[patch],p)
    def label(added):
        return '+'.join(sorted(added)) or 'stock'
    def freeze(seen, p, added):
        key, cur=label(added),snapshot(p)
        if expect is not None:
            need(cur==expect[key], 'declared composition blob mismatch: '+key)
        need(cur==seen.setdefault(key,cur), 'noncommuting patches: '+key)
    for name, blob in COMPONENT_BLOBS.items():
        need(identity(packet/PATCH_NAMES[name])['git_blob']==blob, 'published payload #'+name)
    seen={}
    for i,order in enumerate(permutations(PATCH_IDS)):
        tree=w/f'order-{i}';init(tree)
        applied=[];freeze(seen,tree,applied)
        for name in order:
            apply(tree,name);applied.append(name);freeze(seen,tree,applied)
        while applied:
            apply(tree,applied.pop(),True);freeze(seen,tree,applied)
    need(len(seen)==8,'all eight subsets including stock')
    for dirname,names in (('changed',('r267',)),('composition_base',('571','574')),('composition',PATCH_IDS)):
        t=w/dirname;init(t)
        for n in names:
            apply(t,n)
        freeze(seen,t,names)
    return seen
def main():
    from lift import SOURCES, generate

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--toolchain-bin', type=Path, required=True)
    p.add_argument('--archives', type=Path, action='append', required=True)
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
    need(set(meta["source_inputs"]) == set(SOURCES), "all and only the declared source inputs")
    for f, blob in meta['source_inputs'].items():
        need(identity(src/f)['git_blob'] == blob, "official source: " + f)
    for f, pin in TOOL_PINS.items():
        need(pin == sha((tool/f).read_bytes()) == meta['toolchain_sha256'][f], "toolchain hash: " + f)
    need(meta['only_changed_path'] == CACHE, 'candidate path')
    for n, expected in COMPONENT_BLOBS.items():
        got = identity(HERE/PATCH_NAMES[n])
        need(expected == got['git_blob'] == meta['composition_inputs'][n]['git_blob'] and
             got['sha256'] == meta['composition_inputs'][n]['sha256'], 'published source.patch: #'+n)
    for f in ['Cargo.toml', 'Cargo.lock', 'source.patch']:
        need(sha((HERE/f).read_bytes()) == meta["packet_sha256"][f], "packet digest: " + f)
    with tempfile.TemporaryDirectory(dir=work, prefix='r267-') as temporary:
        w = Path(temporary)
        env = {
            'PATH': str(tool) + ':/usr/bin:/bin', 'HOME': temporary, 'RUSTC': str(tool/'rustc'),
            'CARGO_HOME': str(w/'cargo-home'), 'CARGO_TARGET_DIR': str(w/'target'),
            'TMPDIR': temporary, 'LC_ALL': 'C.UTF-8', 'GIT_CONFIG_GLOBAL': '/dev/null',
            'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CEILING_DIRECTORIES': temporary,
        }
        def run(argv, cwd=None, capture=False):
            return subprocess.run(argv, cwd=cwd or w, env=env, check=True, timeout=600,
                                  stdout=subprocess.PIPE if capture else None, text=True).stdout
        matrix=compile_inputs(src,HERE,w,run,meta['composition_blobs'])
        changed=w/'changed';composed=w/'composition'
        need(matrix['r267'][CACHE]==meta['postimage'], 'standalone candidate postimage')
        for root in [changed, composed]:
            for f in ([CACHE] if root==changed else [VIEW,CACHE]):
                run([tool/'rustfmt', '--edition','2024','--config','skip_children=true','--check',root/f])
        vendorize((src/'Cargo.lock').read_text(), (HERE/'Cargo.lock').read_text(), ars, w/'vendor')
        crate = w/'crate'
        crate.mkdir()
        for f in ('Cargo.lock', 'Cargo.toml'):
            shutil.copyfile(HERE/f, crate/f)
        generate(src, changed, crate/'src', composed)
        # Ensure the composed executable really receives the modified projection
        # and index functions, not just an otherwise compatible patched tree.
        for arm, expected in [('stock', (False, False, False)),
                              ('candidate', (True, False, False)),
                              ('baseline', (False, True, True)),
                              ('composed', (True, True, True))]:
            code = (crate/'src'/arm/'mod.rs').read_text()
            markers = ('.map(|header| (header.source, header.transcript))',
                       'drop(model.conversation);', 'effective_args: tool.effective_args.as_ref(),')
            need(tuple(mark in code for mark in markers) == expected,
                 'incorrect R267 / #571 / #574 source mix in ' + arm)
        cargo = [tool/'cargo', '--offline', '--locked', '--config',
                 'source.crates-io.replace-with="verified"', '--config',
                 'source.verified.directory=' + json.dumps(str(w/'vendor'))]
        records = {}
        for mode in ('default', 'preserve_order'):
            flags = ['--features', 'meter' if mode == 'default' else 'meter,preserve_order']
            graph = run(cargo + ['tree', '-e', 'features'] + flags, crate, True)
            for node in ['ring v0.17.14', 'serde_json v1.0.151', 'serde v1.0.228']:
                need(node in graph, "authentic feature graph: "+node)
            inverse = run(cargo + ['tree', '-e', 'features', '-i', 'serde_json'] + flags, crate, True)
            need(('serde_json feature "preserve_order"' in inverse) == (mode == 'preserve_order'), "serde map mode")
            records[mode] = {}
            for profile in ('release', 'debug'):
                run(cargo + ['build'] + (['--release'] if profile == 'release' else []) + flags, crate)
                exe = w/'target'/profile/'r267-header-proof'
                semantics = run([exe, 'semantics'], capture=True)
                print(f"{mode} {profile}:\n{semantics}", flush=True)
                need('SEMANTICS PASS' in semantics.splitlines(), "missing complete semantic receipt")
                records[mode][profile] = {'semantics': semantics}
                lifetime = run([exe, 'lifetime'], capture=True)
                print(lifetime, flush=True)
                need('LIFETIME PASS' in lifetime.splitlines(), 'missing lifetime receipt')
                records[mode][profile]['lifetime'] = lifetime
            need(records[mode]['release']['semantics'] == records[mode]['debug']['semantics'], "within-mode profile semantic receipt mismatch")
        receipt = {
            'run': 'PASS', 'scope': 'isolated exact-source lift; no full workspace build, RSS, or timing',
            'repository': meta['repository'], 'commit': CORE_COMMIT, 'changed_path': CACHE,
            'stock_blob': meta['source_inputs'][CACHE], 'postimage': meta['postimage'],
            'checked_source_blobs': meta['source_inputs'], 'toolchain_sha256': TOOL_PINS,
            'composition_blobs': matrix, 'apply_and_reverse_permutations': 6,
            'composition_inputs': meta['composition_inputs'],
            'package_archive_count': 38, 'offline_locked': True,
            'package_closure': sha((HERE/'Cargo.lock').read_bytes()), 'map_modes': records,
        }
        out = work/'verification.json'
        with out.open('x') as sink:
            json.dump(receipt, sink, indent=2)
            sink.write('\n')
        print('Verified six three-patch orders and rollbacks, both map modes and profiles, plus the lifetime witnesses.', flush=True)

if __name__ == '__main__':
    main()
