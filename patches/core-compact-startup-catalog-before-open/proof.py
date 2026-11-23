#!/usr/bin/env python3
"""Replay the isolated R268 startup catalog compaction patch with only pinned offline inputs."""
import argparse
import hashlib
import json
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



PREPARED = 'crates/proteus-core/src/core/session_store/remote/prepared.rs'
STOCK = 'a29ae4c880562032b3227565dc8b1cdb59faf6cd'
HISTORICAL_BASE = 'b7fea6bed407cced87a822675ac5596743dea790'
HISTORICAL_COMMIT = '32e56ecb4cc6da324c60dd6ae2da78f3b7e46e7f'
HISTORICAL_PR_HEAD = '07deb04fd66dd33c692c3db1c0d947aee7f6da32'
HISTORICAL_PATCH = '629978d7b5813ec596499cd4894a7ef7da50b69b'
HISTORICAL_SHA256 = 'dd1965c95f8178c8242a684919185acf583bec5efe02b0a6cba339fd05b36417'


def verify_patches(src, packet, work, run, postimage=None):
    """Verify the published #335 base chain and stand-alone R268 rollback."""
    historical = packet/'historical-335.patch'
    got = identity(historical)
    need(got['git_blob'] == HISTORICAL_PATCH and got['sha256'] == HISTORICAL_SHA256,
         'published #335 source.patch bytes')
    root = work/'changed'
    dest = root/PREPARED
    dest.parent.mkdir(parents=True)
    shutil.copyfile(src/PREPARED, dest)

    def apply(patch, forward, expected):
        cmd = ['git','apply','--whitespace=error-all'] + ([] if forward else ['--reverse'])
        stats = run(cmd+['--numstat',patch],root,True).splitlines()
        need(len(stats) == 1 and stats[0].split('\t')[2] == PREPARED, 'one-file patch scope')
        run(cmd+['--check',patch],root)
        run(cmd+[patch],root)
        need([f.relative_to(root).as_posix() for f in root.rglob('*') if f.is_file()] == [PREPARED],
             'only prepared.rs written')
        got = identity(dest)['git_blob']
        if expected is not None:
            need(got == expected, 'exact prepared.rs postimage')
        return got

    need(identity(dest)['git_blob'] == STOCK, 'production Core baseline')
    apply(historical, False, HISTORICAL_BASE)
    apply(historical, True, STOCK)
    patch = packet/'source.patch'
    got = apply(patch, True, postimage)
    apply(patch, False, STOCK)
    apply(historical, False, HISTORICAL_BASE)
    apply(historical, True, STOCK)
    apply(patch, True, got)
    return root, got


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
    need(meta['only_changed_path'] == PREPARED and meta['source_inputs'][PREPARED] == STOCK,
         'exact changed file and Core preimage')
    history = meta['historical_335']
    need(history['before_pr_commit'] == HISTORICAL_COMMIT and history['pr_head'] == HISTORICAL_PR_HEAD and
         history['preimage'] == HISTORICAL_BASE and history['postimage'] == STOCK and
         history['patch_blob'] == HISTORICAL_PATCH and history['patch_sha256'] == HISTORICAL_SHA256,
         'exact historical lineage')
    for f in ['Cargo.toml', 'Cargo.lock', 'source.patch']:
        need(sha((HERE/f).read_bytes()) == meta["packet_sha256"][f], "packet digest: " + f)
    with tempfile.TemporaryDirectory(dir=work, prefix='r268-') as temporary:
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
        changed, postimage = verify_patches(src, HERE, w, run, meta['postimage'])
        run([tool/'rustfmt','--edition','2024','--config','skip_children=true','--check',changed/PREPARED])
        vendorize((src/'Cargo.lock').read_text(), (HERE/'Cargo.lock').read_text(), ars, w/'vendor')
        crate = w/'crate'
        crate.mkdir()
        for f in ('Cargo.lock', 'Cargo.toml'):
            shutil.copyfile(HERE/f, crate/f)
        generate(src, changed, crate/'src')
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
                exe = w/'target'/profile/'r268-catalog-proof'
                semantics = run([exe, 'semantics'], capture=True)
                print(f"{mode} {profile}:\n{semantics}", flush=True)
                need('SEMANTICS PASS' in semantics.splitlines(), "missing complete semantic receipt")
                records[mode][profile] = {'semantics': semantics}
                allocation = run([exe, 'allocation'], capture=True)
                print(allocation, flush=True)
                need('ALLOCATION PASS' in allocation.splitlines(), 'missing allocation receipt')
                records[mode][profile]['allocation'] = allocation
            need(records[mode]['release']['semantics'] == records[mode]['debug']['semantics'], "within-mode profile semantic receipt mismatch")
        receipt = {
            'run': 'PASS', 'scope': 'isolated exact-source lift; no full workspace build, RSS, or timing',
            'repository': meta['repository'], 'commit': CORE_COMMIT, 'changed_path': PREPARED,
            'stock_blob': STOCK, 'postimage': postimage,
            'checked_source_blobs': meta['source_inputs'], 'toolchain_sha256': TOOL_PINS,
            'historical_335': history, 'exact_source_rollbacks': True,
            'package_archive_count': 38, 'offline_locked': True,
            'package_closure': sha((HERE/'Cargo.lock').read_bytes()), 'map_modes': records,
        }
        out = work/'verification.json'
        with out.open('x') as sink:
            json.dump(receipt, sink, indent=2)
            sink.write('\n')
        print('Verified #335 source lineage and R268 rollback, both map modes and profiles, plus the scoped allocation witnesses.', flush=True)

if __name__ == '__main__':
    main()
