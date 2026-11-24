"""Attach a shared additional test module and a deterministic EOF-only test hook."""
from pathlib import Path
import argparse
import shutil

HERE = Path(__file__).resolve().parent
def attach(root):
    src = root / 'storage/session-storage/src'
    subordinate = src / 'tests/r274_native'
    subordinate.mkdir(exist_ok=True)
    tests = src / 'tests/mod.rs'
    data = tests.read_text()
    old_declaration = '\nmod r274_native;\n'
    declaration = '\npub(crate) mod r274_native;\n'
    if old_declaration in data:
        tests.write_text(data.replace(old_declaration,declaration))
    elif declaration not in data:
        tests.write_text(data+declaration)
    shutil.copyfile(HERE / 'native.rs',subordinate / 'mod.rs')
    shutil.copyfile(HERE / 'meter.rs',subordinate / 'meter.rs')
    view = src / 'service/views.rs'
    data = view.read_text()
    axis = '            if source.source_version()? != version {'
    hook = '            #[cfg(test)]\n            crate::tests::r274_native::mutate_at_version_recheck(&dir)?;\n'
    assert data.count(axis) == 1
    if hook not in data:
        view.write_text(data.replace(axis,hook+axis))
if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('workspace',type=Path,nargs='+')
    for src in p.parse_args().workspace:
        attach(src)
