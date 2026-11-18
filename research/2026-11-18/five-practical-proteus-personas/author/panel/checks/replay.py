#!/usr/bin/env python3
"""Compile the example's pure UI, with the real SDK builders and the four used Desktop enum variants."""
import argparse, hashlib, json, pathlib, subprocess, tempfile, time, tomllib, sys
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--sdk-ui', required=True, type=Path)
p.add_argument('--widget', required=True, type=Path)
p.add_argument('--control', required=True, type=Path)
p.add_argument('--serde', required=True, type=Path)
p.add_argument('--serde-json', required=True, type=Path)
p.add_argument('--rustc', required=True, type=Path)
args=p.parse_args()
here=Path(__file__).resolve().parent; example=here.parent/'example'
def quote(path): return json.dumps(str(path.resolve()),ensure_ascii=False)
def lines(path, ranges):
    data=path.read_text().splitlines(keepends=True)
    return ''.join(''.join(data[a-1:b]) for (a,b) in ranges)
def run_timed(argv):
    t=time.perf_counter()
    r=subprocess.run(argv,check=True)
    print('elapsed_seconds=%.3f: %s'%(time.perf_counter()-t,Path(argv[0]).name), flush=True)
sdk=args.sdk_ui.read_bytes()
assert hashlib.sha1(b'blob '+str(len(sdk)).encode()+b'\0'+sdk).hexdigest()=='0bdfb9723583c0e23bab0ffedbbae90a42e25876'
manifest=json.loads((example/'extension.json').read_text())
cargo=tomllib.loads((example/'Cargo.toml').read_text())
assert manifest['protocol']==4 and manifest['id']=='row-tally'
assert manifest['command']==['bin/'+cargo['bin'][0]['name']]
assert set(manifest['surfaces'])=={'panel'} and manifest['dependencies']=={'core':False}
assert set(manifest['required_features'])=={'widgets.controls.v1','manifest.dependencies.core.v1'}
print('Manifest: 5 structural consistency checks (not the Desktop manifest parser).',flush=True)
ext=['--extern','serde='+str(args.serde.resolve()),'--extern','serde_json='+str(args.serde_json.resolve()),'-L','dependency='+str(args.serde.parent.resolve()),'-L','dependency='+str(args.serde_json.parent.resolve())]
with tempfile.TemporaryDirectory() as t:
    d=Path(t)
    (d/'sdk.rs').write_text('pub use serde_json::Value;\n#[path='+quote(args.sdk_ui)+'] pub mod ui;\n')
    lib=d/'libproteus_extension.rlib'
    run_timed([str(args.rustc),'--edition=2024','--crate-type=rlib','--crate-name=proteus_extension',str(d/'sdk.rs'),'-o',str(lib)]+ext)
    # Preserve actual serde tag/deny and full fields: nested button extras are
    # declared as their original public data types; no actual menu/prompt is used.
    schema=lines(args.widget,[(27,29),(259,275),(288,295),(325,351)])+'}\n'+lines(args.widget,[(393,448),(459,467)])
    controls=lines(args.control,[(8,40),(43,55),(59,75)])
    native=(here/'checks.rs.in').read_text().replace('/*SCHEMA*/',schema).replace('/*CTRL*/',controls).replace('PANEL_PATH',quote(example/'src/panel.rs'))
    (d/'test.rs').write_text(native)
    run_timed([str(args.rustc),'--edition=2024','--test',str(d/'test.rs'),'-o',str(d/'test'),'--extern','proteus_extension='+str(lib)]+ext)
    run_timed([str(d/'test'),'--nocapture'])
