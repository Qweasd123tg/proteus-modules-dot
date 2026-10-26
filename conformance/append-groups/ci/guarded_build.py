#!/usr/bin/env python3
"""Single Cargo build with an explicit disk reserve; preserves all artifacts."""
import argparse
import json
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

RESERVE = 1024 ** 3
# Stop before reserve, retaining 128 MiB of margin for concurrent output writes.
STOP_FREE = RESERVE + 128 * 1024 ** 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--binary')
    parser.add_argument('--test-target')
    parser.add_argument('--test-all', action='store_true')
    parser.add_argument('--strip-debug', action='store_true')
    parser.add_argument('--source-root', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    output = args.output.resolve()
    initial = shutil.disk_usage(output).free
    if initial <= STOP_FREE:
        raise RuntimeError(f'insufficient build headroom: {initial} bytes; nothing deleted')
    selected = sum([bool(args.binary), bool(args.test_target), args.test_all])
    if selected != 1:
        parser.error('choose exactly one of --binary, --test-target, --test-all')
    if args.strip_debug and not args.binary:
        parser.error('--strip-debug requires --binary')
    action = 'rustc' if args.strip_debug else ('build' if args.binary else 'test')
    command = ['cargo', action, '--offline', '--locked', '-j2',
               '--manifest-path', str(args.manifest.resolve(strict=True))]
    if args.binary:
        command += ['--bin', args.binary]
    elif args.test_target:
        command += ['--test', args.test_target]
    if args.strip_debug:
        command += ['--', '-C', 'link-arg=-Wl,--strip-debug']
    roots = [args.manifest.resolve().parent, *(root.resolve(strict=True) for root in args.source_root)]
    def source_hashes():
        files = []
        for root in roots:
            files.extend(root / name for name in ('Cargo.toml', 'Cargo.lock', 'rust-toolchain.toml'))
            for sub in ('src', 'tests', 'fixtures', 'examples'):
                files.extend(path for path in (root / sub).rglob('*') if path.is_file())
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(set(files)) if path.is_file()}
    before = source_hashes()
    (output/'source-hashes-before.json').write_text(json.dumps(before, indent=2)+'\n')
    started = time.monotonic()
    samples = []
    stopped = False
    with (output/'stdout.txt').open('w') as stdout, (output/'stderr.txt').open('w') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, start_new_session=True)
        while process.poll() is None:
            free = shutil.disk_usage(output).free
            samples.append({'seconds': round(time.monotonic()-started, 3), 'free_bytes': free})
            if free < STOP_FREE:
                stopped = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                break
            time.sleep(0.1)
    final = shutil.disk_usage(output).free
    after = source_hashes()
    (output/'source-hashes-after.json').write_text(json.dumps(after, indent=2)+'\n')
    result = {'command': command, 'returncode': process.returncode,
              'status': 'stopped_disk_guard' if stopped else ('failed_source_changed' if before!=after else ('passed' if process.returncode==0 else 'failed')),
              'source_hashes_unchanged': before==after,
              'target_only_strip_debug': args.strip_debug,
              'cargo_incremental_env': os.environ.get('CARGO_INCREMENTAL'),
              'initial_free_bytes': initial, 'final_free_bytes': final,
              'minimum_observed_free_bytes': min([initial, final, *(s['free_bytes'] for s in samples)]),
              'reserve_bytes': RESERVE, 'stop_threshold_bytes': STOP_FREE,
              'elapsed_seconds': time.monotonic()-started, 'samples': samples,
              'cleanup': 'No artifacts or caches deleted.'}
    (output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key!='samples'}))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
