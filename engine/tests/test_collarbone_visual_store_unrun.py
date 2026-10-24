# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: temporary immutable paged review transport, not image quality."""
import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib
import pytest
from lumaretouch_engine import collarbone_visual_store as C


def fixture(count=1):
    def chunk(name, data):
        return struct.pack('>I', len(data))+name+data+struct.pack('>I', zlib.crc32(name+data))
    raw = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(b'\0\x22\x44\x66'))+chunk(b'IEND', b'')
    image = {'mime': 'image/png', 'width': 1, 'height': 1, 'sha256': sha256(raw).hexdigest()}
    display = {**image, 'base64': base64.b64encode(raw).decode()}
    targets = []; displays = {}; records = {}
    for index in range(count):
        document = 'document-'+str(index)
        record = {'version': 1, 'document_id': document, 'revision': '3',
            'source_proof': {'original_sha256': 'a'*64, 'asset_sha256': 'a'*64, 'creative_source': None},
            'before_state_sha256': 'b'*64, 'candidate_state_sha256': 'c'*64,
            'before_people_sha256': 'd'*64, 'candidate_people_sha256': 'e'*64,
            'source_size': [1, 1], 'before_output_size': [1, 1], 'after_output_size': [1, 1],
            'coverage_sha256': 'f'*64, 'before': dict(image), 'after': dict(image)}
        targets.append(SimpleNamespace(blocked=None, document_id=document, revision=3,
                                       people_json=json.dumps({'collarbone_visual': record})))
        displays[document] = {'revision': '3', 'before': dict(display), 'after': dict(display)}
        records[document] = record
    plan = SimpleNamespace(token='a'*32, modules=['lnx.collarbone.v1'], targets=targets,
                           params=lambda: {'_people_transfer': {'options': {'target_policy': 'explicit_face_map'}}})
    store = SimpleNamespace(pending={plan.token: plan}, clock=lambda: 0, _prune=lambda now: None)
    def get(token, workspace):
        if token not in store.pending or workspace != 'workspace': raise ValueError('expired or foreign plan')
        return store.pending[token]
    store.get = get
    controller = SimpleNamespace(store=store, versions=SimpleNamespace(workspace='workspace'))
    request = {'cmd': 'batch', 'action': 'collarbone_visual', 'request_id': 'read-one',
               'preflight_token': plan.token, 'document_id': 'document-0', 'revision': '3',
               'side': 'before', 'sha256': image['sha256']}
    return controller, plan, displays, records, request, raw


def test_sixteen_targets_are_compact_and_each_side_is_retrievable():
    owner, plan, displays, records, request, raw = fixture(16)
    C.attach(owner.store, plan, displays); C.verify_available(owner.store, plan)
    assert owner.store._collarbone_visual_images.count == 32
    assert 'base64' not in ''.join(target.people_json for target in plan.targets)
    for document in records:
        for side in ('before', 'after'):
            result = C.retrieve(owner, {**request, 'document_id': document, 'side': side})
            assert result['document_id'] == document and result['side'] == side
            assert base64.b64decode(result['image']['base64']) == raw


@pytest.mark.parametrize('key,value', [('preflight_token', 'b'*32), ('document_id', '../other'), ('revision', '4'), ('side', '../before'), ('sha256', '0'*64)])
def test_request_cannot_substitute_token_target_revision_side_or_hash(key, value):
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    with pytest.raises(ValueError): C.retrieve(owner, {**request, key: value})


def test_extra_request_fields_cannot_supply_path_or_effect():
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    for key in ('path', 'amount', 'people_transfer', 'collarbone_review_ack'):
        with pytest.raises(ValueError): C.retrieve(owner, {**request, key: 'injected'})


def test_changed_image_is_rejected_before_read_and_commit():
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images
    cache.plans[plan.token]['document-0']['before']['path'].write_bytes(b'corrupt')
    with pytest.raises(ValueError): C.retrieve(owner, request)
    with pytest.raises(ValueError): C.verify_available(owner.store, plan)


def test_missing_image_never_regenerates_or_promotes_thumbnail():
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    owner.store._collarbone_visual_images.plans[plan.token]['document-0']['before']['path'].unlink()
    with pytest.raises(ValueError): C.retrieve(owner, request)
    with pytest.raises(ValueError): C.verify_available(owner.store, plan)


def test_consumed_or_expired_plan_removes_session_images():
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images
    paths = [entry['path'] for row in cache.plans[plan.token].values() for entry in row.values()]
    owner.store.pending.clear(); C.prune(owner.store)
    assert not cache.plans and cache.bytes == 0 and cache.count == 0
    assert all(not path.exists() for path in paths)
    with pytest.raises(ValueError): C.retrieve(owner, request)


def test_global_budget_is_atomic_without_reducing_or_omitting_targets(monkeypatch):
    owner, plan, displays, _, _, raw = fixture(2)
    monkeypatch.setattr(C, 'MAX_BYTES', len(raw)*3)
    with pytest.raises(ValueError, match='budget'): C.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images
    assert not cache.plans and cache.bytes == 0 and cache.count == 0
    assert not list(Path(cache.directory.name).iterdir())


def test_duplicate_attachment_cannot_replace_immutable_review():
    owner, plan, displays, _, _, _ = fixture(); C.attach(owner.store, plan, displays)
    with pytest.raises(ValueError, match='already owns'): C.attach(owner.store, plan, displays)
    C.verify_available(owner.store, plan)


def test_copied_plan_object_is_not_live_attachment_authority():
    owner, plan, displays, _, _, _ = fixture()
    with pytest.raises(ValueError, match='actual live'): C.attach(owner.store, deepcopy(plan), displays)


def test_wrong_display_digest_fails_without_retained_files():
    owner, plan, displays, _, _, _ = fixture()
    displays['document-0']['after']['base64'] = base64.b64encode(b'other bytes').decode()
    with pytest.raises(ValueError, match='content verification'): C.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images
    assert not cache.plans and cache.count == 0 and cache.bytes == 0


def test_cleanup_failure_retains_budget_reservation_until_retry(monkeypatch):
    owner, plan, displays, _, _, _ = fixture(); C.attach(owner.store, plan, displays)
    cache = owner.store._collarbone_visual_images; prior = cache.bytes
    owner.store.pending.clear()
    def denied(self, **kwargs): raise OSError('fixture deletion failure')
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'unlink', denied); C.prune(owner.store)
        assert cache.bytes == prior and cache.count == 2 and plan.token in cache.plans
    C.prune(owner.store)
    assert cache.bytes == 0 and cache.count == 0


def test_expired_read_prunes_blobs_even_when_get_raises():
    owner, plan, displays, _, request, _ = fixture(); C.attach(owner.store, plan, displays)
    def expired(token, workspace):
        owner.store.pending.clear()
        raise ValueError('expired')
    owner.store.get = expired
    with pytest.raises(ValueError, match='expired'): C.retrieve(owner, request)
    cache = owner.store._collarbone_visual_images
    assert not cache.plans and cache.bytes == 0 and cache.count == 0
