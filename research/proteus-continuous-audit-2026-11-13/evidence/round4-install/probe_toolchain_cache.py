#!/usr/bin/env python3
"""Production prepare/download/flatten, local source archives, fake Zig fetch only."""
import hashlib,io,json,os,pathlib,shutil,sys,tarfile
from unittest.mock import patch
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,'/workspace/shared/install-build-round4/scripts')
import terminal_toolchain as t
base=HERE/'toolchain-cache-fixture'
if base.exists():shutil.rmtree(base)
base.mkdir()
zig=base/'fake-zig'
zig.write_text('''#!/usr/bin/env python3
import hashlib,json,os,pathlib,sys,tarfile
cache=pathlib.Path(os.environ['ZIG_GLOBAL_CACHE_DIR'])/'p';cache.mkdir(parents=True,exist_ok=True)
if sys.argv[1]=='version': print('0.17.0')
elif sys.argv[1]=='env': print('.global_cache_dir = '+json.dumps(str(cache.parent)))
elif sys.argv[1]=='fetch':
 with tarfile.open(sys.argv[2]) as tar: data=tar.extractfile('build.zig.zon').read()
 digest=hashlib.sha256(data).hexdigest()
 (cache/(digest+'.tar.gz')).write_bytes(data)
 print(digest)
''');zig.chmod(0o755)
archives={};hashes={}
for v in ('A','B'):
    path=base/f'package-{v}.tar.gz';data=f'package revision {v}'.encode()
    with tarfile.open(path,'w:gz') as tar:
        member=tarfile.TarInfo('upstream/build.zig.zon');member.size=len(data);tar.addfile(member,io.BytesIO(data))
    archives[v]=path;hashes[v]=hashlib.sha256(data).hexdigest()
env=dict(os.environ,ZIG=str(zig),ZIG_GLOBAL_CACHE_DIR=str(base/'zig-cache'))
root=base/'warm-checkout'
with patch.object(t,'PACKAGES',[('fixture',archives['A'].as_uri(),hashes['A'])]):t.prepare(root,env)
archive=root/'build/tools/ghostty-deps/fixture.tar.gz'
before=hashlib.sha256(archive.read_bytes()).hexdigest()
error=None
try:
    with patch.object(t,'PACKAGES',[('fixture',archives['B'].as_uri(),hashes['B'])]):t.prepare(root,env)
except RuntimeError as e:error=str(e)
assert error is not None and 'expected Zig hash' in error
assert hashlib.sha256(archive.read_bytes()).hexdigest()==before
with patch.object(t,'PACKAGES',[('fixture',archives['B'].as_uri(),hashes['B'])]):t.prepare(base/'fresh-checkout',env)
result={'warm_A_to_B':error,'cached_archive_still_A':True,'fresh_B':'passed','fixture_note':'fake Zig emits sha256 of unpacked file in place of Zig content hash; download/flatten/receipt/prepare are unmodified production code'}
print(json.dumps(result,indent=2));(HERE/'toolchain-cache-result.json').write_text(json.dumps(result,indent=2)+'\n')
