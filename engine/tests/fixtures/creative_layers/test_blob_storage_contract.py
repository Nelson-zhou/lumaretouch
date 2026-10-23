"""AUTHORED / UNRUN. Qoder owns execution, disk-fault and resource acceptance.

Includes a deliberately opt-in 24 MP full-float fixture, not a small-image claim
about production memory or timing. No precision reduction is permitted.
"""
import copy
import json
import os
import struct

import pytest

from lumaretouch_engine import creative_document_storage as B


def transport(raw):
    assets = {}
    value = B.encode_bytes(raw, assets)
    return {'assets': assets, 'docs': [{'recipe': {'content': value}}]}, value


def test_chunk_boundary_roundtrip_and_exact_complete_digest():
    raw = b'a' * B.CHUNK_BYTES + b'last exact bytes'
    project, marker = transport(raw)
    assert len(marker['chunks']) == 2
    assert all(row['bytes'] <= 7_000_000 for row in project['assets'].values())
    assert B.decode_bytes(marker, project['assets']) == raw
    stored, blobs = B.pack(project)
    assert len(json.dumps(stored)) < 10_000
    assert B.hydrate(stored, blobs) == project
    assert b''.join(blobs[key] for key in marker['chunks']) == raw


def test_decode_cache_is_bounded_without_mutating_asset_tables(monkeypatch):
    cache = B._DecodedBytes()
    monkeypatch.setattr(B, 'MAX_STORE_BYTES', 32)
    kept = b'a' * 20
    assert cache.put(('first',), kept) is kept
    cache.put(('second',), b'b' * 20)
    assert cache.get(('first',)) is None
    assert cache.bytes == 20
    assert kept == b'a' * 20  # Cache eviction cannot mutate an owned history value.


@pytest.mark.parametrize('damage', ['reorder', 'missing', 'full-hash', 'count', 'length', 'extra'])
def test_chunk_marker_never_falls_back_to_lossy_best_effort(damage):
    project, value = transport(b'a' * B.CHUNK_BYTES + b'b' * B.CHUNK_BYTES)
    marker = copy.deepcopy(value)
    if damage == 'reorder': marker['chunks'].reverse()
    elif damage == 'missing': del project['assets'][marker['chunks'][0]]
    elif damage == 'full-hash': marker['sha256'] = 'sha256:' + '0' * 64
    elif damage == 'count': marker['chunks'].pop()
    elif damage == 'length': marker['bytes'] -= 1
    elif damage == 'extra': marker['path'] = '../../untrusted'
    with pytest.raises(ValueError):
        B.decode_bytes(marker, project['assets'])


def test_sidecar_requires_all_exact_bytes_and_rejects_unlisted_payload(tmp_path):
    project, _ = transport(b'canonical bytes including original source and ICC')
    stored, blobs = B.pack(project)
    path = tmp_path / 'project.lrproject.json'
    B.write_blobs(stored, blobs, path, reserve_bytes=0)
    assert B.read_blobs(stored, path) == blobs
    for broken in ({}, {**blobs, 'sha256:' + '0' * 64: b'extra'}):
        with pytest.raises(ValueError):
            B.hydrate(stored, broken)
    key = next(iter(blobs))
    broken = copy.deepcopy(stored)
    broken['assets'][key]['blob'] = '../../escape'
    with pytest.raises(ValueError):
        B.read_blobs(broken, path)


def test_symlink_blob_and_sidecar_are_rejected(tmp_path):
    project, _ = transport(b'owned source pixels')
    stored, blobs = B.pack(project)
    path = tmp_path / 'project.lrproject.json'
    root = B.sidecar_path(path)
    root.mkdir()
    source = tmp_path / 'unowned.bin'
    source.write_bytes(next(iter(blobs.values())))
    key = next(iter(blobs))
    (root / key[7:]).symlink_to(source)
    with pytest.raises((ValueError, OSError)):
        B.read_blobs(stored, path)
    (root / key[7:]).unlink()
    root.rmdir()
    other = tmp_path / 'other'
    other.mkdir()
    root.symlink_to(other, target_is_directory=True)
    with pytest.raises(ValueError):
        B.write_blobs(stored, blobs, path, reserve_bytes=0)


def test_reserve_failure_does_not_evict_existing_generation(tmp_path, monkeypatch):
    first, _ = transport(b'old snapshot required by history')
    stored, blobs = B.pack(first)
    path = tmp_path / 'project.lrproject.json'
    B.write_blobs(stored, blobs, path, reserve_bytes=0)
    second, _ = transport(b'new independent snapshot')
    new_stored, new_blobs = B.pack(second)
    usage = type('Usage', (), {'free': 0})()
    monkeypatch.setattr(B.shutil, 'disk_usage', lambda _: usage)
    with pytest.raises(ValueError, match='reserve'):
        B.write_blobs(new_stored, new_blobs, path, reserve_bytes=1)
    assert B.read_blobs(stored, path) == blobs


def test_sidecar_keeps_unreferenced_old_generations_without_gc(tmp_path):
    path = tmp_path / 'history.lrproject.json'
    old, _ = transport(b'old retained version')
    old_stored, old_blobs = B.pack(old)
    new, _ = transport(b'new active version')
    new_stored, new_blobs = B.pack(new)
    B.write_blobs(old_stored, old_blobs, path, reserve_bytes=0)
    B.write_blobs(new_stored, new_blobs, path, reserve_bytes=0)
    assert B.read_blobs(old_stored, path) == old_blobs
    assert B.read_blobs(new_stored, path) == new_blobs


@pytest.mark.skipif(os.environ.get('LRT_RUN_LARGE_CREATIVE_FIXTURES') != '1',
                    reason='Opt-in 24 MP memory/disk qualification; AUTHORED / UNRUN')
def test_24mp_full_float_roundtrip_without_raising_manifest_or_asset_caps(tmp_path):
    # Exactly 24,000,000 premultiplied RGBA float32 pixels = 384,000,000 bytes.
    raw = b''.join(struct.pack('<ffff', .123456791 + index * .001,
                              -.012345679, 1.23456788, 1.0) * (min(B.CHUNK_BYTES, 384_000_000 - start) // 16)
                   for index, start in enumerate(range(0, 384_000_000, B.CHUNK_BYTES)))
    project, marker = transport(raw)
    stored, blobs = B.pack(project)
    assert marker['bytes'] == 384_000_000
    assert sum(len(block) for block in blobs.values()) == 384_000_000
    assert len(json.dumps(stored).encode()) < 64_000_000 < 256_000_000
    assert max(row['bytes'] for row in stored['assets'].values()) <= 7_000_000 < 8_000_000
    path = tmp_path / '24mp.lrproject.json'
    B.write_blobs(stored, blobs, path)
    hydrated = B.hydrate(stored, B.read_blobs(stored, path))
    assert B.decode_bytes(marker, hydrated['assets']) == raw
