"""Compare the validated paste source and unchanged UndoManager from two Desktop trees."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile


def verified(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f'Unexpected source digest: {path}. Use the pinned revision and patch.')
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--rustc', default='rustc')
    args = parser.parse_args()
    source_dir = Path('vendor/gpui-base/src/input/base')
    fixture = Path(__file__).with_name('paste_probe.rs.in').read_text()
    state_sha = {
        'before': '4af9654ea6f3c07287fc3870ff2d7b5512288767d6efe13a7c9739789a6e7a8d',
        'after': 'bee4c8f68dd9b1fa785b81ef26dcc5e961b6303a6655a066552b74fc291eeea9',
    }
    unchanged = {
        'undo_manager.rs': 'c71d0526c182b881280159c52b749253bfcbc0e3d3819a37cd3f0eec88db7244',
        'change.rs': '7555a8bd9067a7f19248c2140c9836ea0f68ad80640210b95e886b01b91b9599',
    }
    for label, tree in [('before', args.baseline), ('after', args.candidate)]:
        state = verified(tree / source_dir / 'state.rs', state_sha[label]).decode()
        start = state.index('    fn insert_clipboard(')
        end = state.index('\n    /// The intent of a batch', start)
        with tempfile.TemporaryDirectory(prefix='textarea-paste-') as scratch:
            work = Path(scratch)
            for name, digest in unchanged.items():
                (work / name).write_bytes(verified(tree / source_dir / name, digest))
            (work / 'main.rs').write_text(fixture.replace('@INSERT@', state[start:end]))
            cmd = [args.rustc, '--edition', '2024', '-C', 'opt-level=1']
            if label == 'after':
                cmd += ['--cfg', 'candidate']
            subprocess.run(cmd + ['main.rs', '-o', 'check'], cwd=work, check=True)
            print(label, flush=True)
            subprocess.run([str(work / 'check')], cwd=work, check=True)


if __name__ == '__main__':
    main()
