#!/usr/bin/env python3
"""Archive only owned regular evidence files; verify every payload before upload."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def archive(source, target, manifest, max_file=8*1024**2, max_total=256*1024**2):
    source, target, manifest = source.resolve(strict=True), target.absolute(), manifest.absolute()
    if not source.is_dir() or target.is_relative_to(source) or manifest.is_relative_to(source):
        raise ValueError('archive and manifest must be outside the evidence directory')
    if target.exists() or manifest.exists():
        raise ValueError('archive outputs must be new')
    files = []
    total = 0
    for path in sorted(source.rglob('*')):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError('nonregular evidence entry: ' + str(path.relative_to(source)))
        if stat.S_ISDIR(mode):
            continue
        size = path.stat().st_size
        total += size
        if size > max_file or total > max_total:
            raise ValueError('evidence size bound exceeded')
        files.append({'path': str(Path('append-groups') / path.relative_to(source)),
                      'bytes': size, 'sha256': digest(path)})
    if not files:
        raise ValueError('evidence directory is empty')
    with tarfile.open(target, mode='x:gz', format=tarfile.PAX_FORMAT) as output:
        for entry in files:
            path = source / Path(entry['path']).relative_to('append-groups')
            output.add(path, arcname=entry['path'], recursive=False)
    expected = {entry['path']: entry for entry in files}
    with tarfile.open(target, mode='r:gz') as check:
        members = check.getmembers()
        if len(members) != len(expected) or {member.name for member in members} != set(expected):
            raise ValueError('archive inventory mismatch')
        for member in members:
            name = Path(member.name)
            if not member.isreg() or name.is_absolute() or '..' in name.parts:
                raise ValueError('unsafe archive member')
            entry = expected[member.name]
            stream = check.extractfile(member)
            if member.size != entry['bytes'] or hashlib.file_digest(stream, 'sha256').hexdigest() != entry['sha256']:
                raise ValueError('archive payload mismatch')
            original = source / name.relative_to('append-groups')
            if original.stat().st_size != entry['bytes'] or digest(original) != entry['sha256']:
                raise ValueError('source changed during archive creation')
    receipt = {'schema_version': 1, 'scope': 'owned evidence packaging, not new Core execution',
               'github_sha': os.environ.get('GITHUB_SHA'), 'github_run_id': os.environ.get('GITHUB_RUN_ID'),
               'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
               'archive': {'file': target.name, 'bytes': target.stat().st_size, 'sha256': digest(target)},
               'files': files, 'all_payloads_verified': True, 'source_unchanged': True,
               'hidden_files_included': True, 'source_files_deleted': False}
    with manifest.open('x') as output:
        json.dump(receipt, output, indent=2)
        output.write('\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    result = archive(args.source, args.archive, args.manifest)
    print(json.dumps({'files': len(result['files']), 'archive': result['archive'], 'all_payloads_verified': True}))


if __name__ == '__main__':
    main()
