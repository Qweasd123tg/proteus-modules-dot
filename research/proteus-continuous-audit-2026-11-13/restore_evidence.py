#!/usr/bin/env python3
"""Verify archived bytes and restore selected evidence into a new directory.

No subprocess, network, package installation or reproducer execution.
"""
import argparse
import gzip
import hashlib
import json
import io
import tarfile
from functools import lru_cache
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'Unsafe manifest path: {value!r}')
    return Path(*path.parts)


@lru_cache(maxsize=None)
def read_container(path, checksum, length):
    data = path.read_bytes()
    if len(data) != length or hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError(f'Container checksum mismatch: {path.name}')
    members = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive:
            relative(member.name)
            if not member.isfile() or member.name in members:
                raise ValueError('Non-regular or duplicate archive member')
            members[member.name] = archive.extractfile(member).read()
    return members


def checked_bytes(entry):
    path = ROOT / relative(entry['path'])
    if 'member' in entry:
        raw = read_container(path, entry['sha256'], entry['bytes'])[entry['member']]
        if len(raw) != entry['original_bytes'] or hashlib.sha256(raw).hexdigest() != entry['original_sha256']:
            raise ValueError(f'Original checksum mismatch: {entry["original_path"]}')
        raw.decode('utf-8')
        return path, raw
    data = path.read_bytes()
    if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
        raise ValueError(f'Stored checksum mismatch: {entry["path"]}')
    raw = gzip.decompress(data) if entry['path'] != entry['original_path'] else data
    if len(raw) != entry['original_bytes'] or hashlib.sha256(raw).hexdigest() != entry['original_sha256']:
        raise ValueError(f'Original checksum mismatch: {entry["original_path"]}')
    raw.decode('utf-8')
    return path, raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--output', type=Path, help='new, nonexistent output directory')
    parser.add_argument('--group', action='append', help='canonical group id; repeatable')
    args = parser.parse_args()
    if args.verify_only == bool(args.output):
        parser.error('choose exactly one of --verify-only or --output')
    manifest = json.loads((ROOT / 'MANIFEST.json').read_text())
    known = {g['id'] for g in manifest['groups']}
    chosen = set(args.group or known)
    if not chosen <= known:
        parser.error(f'unknown group(s): {sorted(chosen - known)}')
    entries = [e for e in manifest['files'] if relative(e['original_path']).parts[1] in chosen]
    destinations = [relative(e['original_path']) for e in entries]
    if len(destinations) != len(set(destinations)):
        raise ValueError('Duplicate output paths')
    # Verify every selected entry before creating any output.
    for entry in entries:
        checked_bytes(entry)
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        for entry, rel in zip(entries, destinations):
            src, raw = checked_bytes(entry)
            dest = args.output / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(raw)
            dest.chmod(src.stat().st_mode & 0o777)
    print(f'PASS: {len(entries)} evidence files, {len(chosen)} group(s); no tests executed')


if __name__ == '__main__':
    main()
