"""Replay exact M395 Cosmic font inventory with native fontdb and gpui value slices."""
from pathlib import Path
import argparse,base64,gzip,hashlib,json,os,re,subprocess,tempfile,sys
sys.dont_write_bytecode=True
from lift import lift
P=Path(__file__).resolve().parent
def oid(b):return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
def sha(b):return hashlib.sha256(b).hexdigest()
def outcome(log,host=False):
    assert ('test result: ok. 1 passed; 0 failed;' if host else 'test result: ok. 2 passed; 0 failed; 1 ignored;') in log
    rows=re.findall(r'FONT (\S+) '+' '.join([r'(-?\d+)']*8),log);assert len(rows)==(1 if host else 5)
    return {label:list(map(int,nums)) for label,*nums in rows}
def audit(s):
    m=s['src/main.rs'];assert m.index('.add_fonts(')<m.index('gpui_kit::init(cx);')<m.index('ui::init(cx, preferences);')<m.index('gpui_kit::open_window(')
    assert 'gpui_component::init(cx);' in s['witness/gpui_kit_lib.rs']
    ci=s['vendor/gpui-component/src/lib.rs'];assert '    theme::init(cx);' in ci
    assert 'Theme::change(ThemeMode::Light, None, cx);' in s['vendor/gpui-component/src/theme/mod.rs']
    assert 'NAMES.get_or_init(|| cx.text_system().all_font_names())' in s['vendor/gpui-component/src/theme/mono_font.rs']
    assert 'let installed = installed_font_names(cx);' in s['vendor/gpui-component/src/theme/system_font.rs']
    assert 'fonts::init(cx);' in s['src/ui/theme/mod.rs']
    assert 'let mut names = self.platform_text_system.all_font_names();' in s['vendor/gpui-fast/src/text_system.rs']
    assert 'db.load_system_fonts();' in s['witness/cosmic_font_system.rs']
    assert 'let font_system = FontSystem::new();' in s['vendor/gpui-fast-wgpu/src/cosmic_text_system.rs']

def main():
    p=argparse.ArgumentParser();p.add_argument('--vendor',type=Path)
    p.add_argument('--noto',type=Path,help='optional exact bundled test asset; also exercises current Linux system fonts')
    a=p.parse_args()
    r=json.loads((P/'receipt.json').read_bytes())
    dat=base64.b64decode(b''.join((P/n).read_bytes().strip() for n in r['source_shards']))
    assert sha(dat)==r['capsule_hash']
    s=json.loads(gzip.decompress(dat));assert {n:oid(v.encode()) for n,v in s.items()}==r['source_blobs'];audit(s)
    patch=(P/'source.patch').read_bytes();assert sha(patch)==r['patch_sha256']
    lock=(P/'Cargo.lock').read_text();assert sha(lock.encode())==r['proof_lock_sha256']
    cargo=['cargo']
    if a.vendor:
        cargo+=['--offline','--config','source.crates-io.replace-with="verified"','--config',f'source.verified.directory="{a.vendor.resolve()}"']
    host={}
    if a.noto:
        assert oid(a.noto.read_bytes())==r['bundled_noto_git_blob']
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for side in ('stock','candidate'):
            d=root/side;source=d/'product'
            for n,v in s.items():
                f=source/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(v)
            if side=='candidate':
                for opts in (['--check'],[]):
                    subprocess.run(['git','apply','--whitespace=error',*opts,'-'],cwd=source,input=patch,check=True)
                assert {n:oid((source/n).read_bytes()) for n in r['candidate_blobs']}==r['candidate_blobs']
                subprocess.run(['git','apply','-R','-'],cwd=source,input=patch,check=True)
                assert all((source/n).read_bytes()==v.encode() for n,v in s.items())
                subprocess.run(['git','apply','-'],cwd=source,input=patch,check=True)
            lift({n:(source/n).read_text() for n in s},d/'src',P)
            name=f'desktop-font-inventory-proof-{side}'
            (d/'Cargo.toml').write_text((P/'Cargo.toml').read_text().replace('desktop-font-inventory-proof',name))
            (d/'Cargo.lock').write_text(lock.replace('desktop-font-inventory-proof',name))
            env={**os.environ,'CARGO_TARGET_DIR':str(root/'target'),'CARGO_INCREMENTAL':'0'}
            def run(extra):
                p=subprocess.run(cargo+['test','--release','--locked','-j2',*extra],
                    env=env,cwd=d,capture_output=True,text=True)
                if p.returncode:print(p.stdout+p.stderr,flush=True)
                p.check_returncode()
                return p.stdout
            data=outcome(run(['--','--test-threads=1','--nocapture']))
            assert data==r['runs'][side]['portable'],(side,data)
            print(side,'native font cases',data,flush=True)
            if a.noto:
                env['PROOF_NOTO']=str(a.noto.resolve())
                host[side]=outcome(run(['real_system_font_database','--','--ignored','--test-threads=1','--nocapture']),True)['system']
                print(side,'native host catalogue',host[side],flush=True)
    if host:
        b,c=host['stock'],host['candidate']
        assert b[:2]==c[:2] and b[3]==c[3] and c[2]==c[1]
if __name__=='__main__':main()
