"""Pure source replay. Run with a Desktop checkout matching this selector."""
import hashlib, json, subprocess, sys
from pathlib import Path
from tempfile import TemporaryDirectory
P=Path(__file__).resolve().parent
def oid(data): return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
receipt=json.loads((P/'receipt.json').read_text())
pin=receipt['source']
checkout=Path(sys.argv[1]).resolve()
src=pin['path']
source=(checkout/src).read_bytes()
assert oid(source)==pin['before_git_oid']
for pathname, compare in json.loads((P/'source-pins.json').read_text())['files'].items():
    b=(checkout/pathname).read_bytes()
    assert [len(b),oid(b)]==compare[1:],pathname
with TemporaryDirectory(prefix='replay-thumbnail-') as t:
    path=Path(t)/src
    path.parent.mkdir(parents=True)
    path.write_bytes(source)
    patch=P/'source.patch'
    def apply(*a):
        subprocess.run(['git','apply','--whitespace=error',*a,str(patch)],cwd=t,check=True)
    apply('--check')
    apply()
    assert oid(path.read_bytes())==pin['after_git_oid']
    apply('--reverse','--check')
    apply('--reverse')
    assert path.read_bytes()==source
print(f'exact replay + reverse {pin["before_git_oid"]} -> {pin["after_git_oid"]}, 7 context pins')
