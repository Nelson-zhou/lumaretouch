#!/usr/bin/env python3
"""Validate declared bundled weights against staged bytes; not a legal clearance."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

WEIGHT_SUFFIXES = {'.task', '.tflite', '.onnx', '.pth', '.pt', '.ckpt', '.safetensors'}


def validate(ledger: dict, stage: Path) -> list[str]:
    errors = []
    models = ledger.get('models', [])
    by_name = {}
    for m in models:
        name = m.get('artifact')
        if name:
            if name in by_name:
                errors.append(f'duplicate artifact entry: {name}')
            by_name[name] = m
        if m.get('tier') != 'bundled':
            continue
        if not name or Path(name).name != name:
            errors.append(f"{m.get('id')}: bundled artifact must be a filename")
        hashes = [m[k] for k in ('sha256', 'artifact_sha256') if m.get(k)]
        if not hashes or any(not re.fullmatch(r'[0-9a-f]{64}', h) for h in hashes):
            errors.append(f'{name}: missing or invalid sha256')
        elif len(set(hashes)) != 1:
            errors.append(f'{name}: conflicting declared hashes')
        if m.get('evidence') != '一手':
            errors.append(f'{name}: missing primary license evidence')
        license_name = m.get('weights_license') or m.get('license')
        if not license_name or str(license_name).lower() in {'unknown','none','unverified'}:
            errors.append(f'{name}: missing weights license')
        if not isinstance(m.get('size_bytes'), int) or isinstance(m.get('size_bytes'), bool) or m['size_bytes'] <= 0:
            errors.append(f'{name}: invalid declared size')
    if not stage.is_dir():
        return errors + [f'stage directory missing: {stage}']
    found = {}
    for p in stage.rglob('*'):
        if p.suffix.lower() not in WEIGHT_SUFFIXES and p.name not in by_name:
            continue
        if p.is_symlink():
            errors.append(f'{p.name}: weight symlink not allowed')
            continue
        if not p.is_file():
            continue
        m = by_name.get(p.name)
        if m is None:
            errors.append(f'unlisted weight: {p.relative_to(stage)}')
            continue
        found.setdefault(p.name, []).append(p)
        if m.get('tier') != 'bundled':
            errors.append(f'{p.name}: staged but tier is {m.get("tier")}')
            continue
        if p.stat().st_size != m.get('size_bytes'):
            errors.append(f'{p.name}: size mismatch')
        h = hashlib.sha256()
        with p.open('rb') as f:
            for block in iter(lambda: f.read(1024*1024), b''):
                h.update(block)
        if h.hexdigest() != m.get('sha256'):
            errors.append(f'{p.name}: sha256 mismatch')
    for m in models:
        if m.get('tier') == 'bundled':
            paths = found.get(m.get('artifact'), [])
            if len(paths) != 1:
                errors.append(f'{m.get("artifact")}: expected one bundled file, found {len(paths)}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',type=Path)
    parser.add_argument('--ledger',type=Path,default=Path('docs/model-licenses/models.json'))
    args=parser.parse_args()
    try:
        errors=validate(json.loads(args.ledger.read_text()),args.stage)
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(f'× model artifact validation failed: {e}')
        return 1
    if errors:
        print('× model artifact gate:\n'+'\n'.join('  '+e for e in errors))
        return 1
    print('✓ model artifact hashes, sizes, inventory and declared evidence match; legal review remains separate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
