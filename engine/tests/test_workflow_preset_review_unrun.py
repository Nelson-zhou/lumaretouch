"""Authored, NOT executed: scalar workflow review ownership contracts.

The renderer double below proves transport/lifecycle wiring only. It is not
pixel-quality, native-engine, GPU, inference or end-to-end acceptance evidence.
"""
from base64 import b64decode
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from lumaretouch_engine import workflow_preset_review as R
from lumaretouch_engine import workflow_preset_catalogue as C
from lumaretouch_engine import preset_store as PS
from lumaretouch_engine import scope as SC
from lumaretouch_engine import white_balance_recipe as WB
from lumaretouch_engine import full_candidate_render as FULL
from lumaretouch_engine import portrait_review_render as DISPLAY
from lumaretouch_engine import virtual_copy_people as V
from lumaretouch_engine import document_versions as DV
from lumaretouch_engine.local_mask_state import file_stamp
from lumaretouch_engine.people_graph_owner import PeopleGraphOwner


class Engine:
    def __init__(self, path):
        self.state = {'_exposure': (0.1, 100., 0.02, 0.2, 0.3, 0.4, 0.5),
            '_exposure_ref_k': 5500., '_wb_options': WB.default_options(),
            '_creative_base': None, '_precompute': None, '_repair_ops': [], '_redo_ops': [],
            '_retained_other_effect': {'amount': 0.42}}
        self._docs = [{'path': str(path), 'src_w': 256, 'src_h': 256, 'state': deepcopy(self.state),
                       '_local_source_stamp': file_stamp(path)}]
        self._doc_index = 0
        self._document_version_owner = DV.DocumentVersions()
        self._document_version_owner.version(self._docs[0])  # Fixture simulates the completed load owner.
        self._load_id = 'loaded-123'
        self._doc_path = str(path)
        self._creative_base = None
        self._people_graph_owner = PeopleGraphOwner()
        self._people_scope_row = self._docs[0]
        self._people_active_context = {'owner': self._people_graph_owner, 'analyses': {}}
        for key, field in V.FIELDS.items():
            setattr(self, field, {})
            self._people_active_context[key] = getattr(self, field)
        self._people_project_context = self._people_active_context
        self.guard_reason = None
        self.render_calls = []
        self.unrelated_snapshot_input = 'preserved'

    def _document_versions(self):
        return self._document_version_owner

    def _guard_editable(self, _label):
        return self.guard_reason

    def _people_preset_capture(self):
        return deepcopy(self.state)

    def _state_to_export_snap(self, state, **options):
        # Deliberately tiny snapshot double, not the real export pipeline.
        assert options['source_path'] == self._doc_path
        assert options['people_document_id'] == self._docs[0]['document_id']
        return {'state': deepcopy(state), 'people': None,
                'unrelated_snapshot_input': self.unrelated_snapshot_input}

    def __getattr__(self, name):
        if name in ('_replay_state', '_people_preset_replay', '_remember_current', '_fence_current_document',
                    '_history', '_undo', '_redo', 'cmd_preset', 'cmd_load_image', 'cmd_project'):
            raise AssertionError('Review must never read history or invoke an application owner: ' + name)
        raise AttributeError(name)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(PS, 'preset_dir', lambda: str(tmp_path / 'absent-presets'))
    pixels = np.random.default_rng(12).integers(0, 256, (256, 256, 3), dtype=np.uint8)
    path = tmp_path / 'original.png'
    Image.fromarray(pixels, 'RGB').save(path)
    engine = Engine(path)
    now = [100.]
    owner = R.WorkflowPresetReviews(engine, clock=lambda: now[0])
    target = {'document_id': engine._docs[0]['document_id'], 'load_id': engine._load_id, 'revision': '0'}
    preset_hash = C.fingerprint('color-warm')

    def renderer(host, row, state, document_id, revision, *, people_graph=None, cancelled=lambda: False, **kwargs):
        assert host is engine and row is engine._docs[0] and not kwargs
        assert not cancelled()
        engine.render_calls.append((deepcopy(state), people_graph))
        proof, _, _ = FULL.identity(host, row, state, document_id, revision, people_graph=people_graph)
        # Only transport determinism is under test, never the actual exposure kernel.
        rgb = np.roll(pixels, int(state['_exposure'][0] * 100), axis=1).astype(np.float32) / 255.
        return rgb, {**proof, 'source_size': [256, 256], 'output_size': [256, 256]}

    monkeypatch.setattr(FULL, 'render', renderer)
    return SimpleNamespace(engine=engine, owner=owner, target=target, preset_hash=preset_hash,
                           now=now, path=path, renderer=renderer)


def prepare(f):
    return f.owner.prepare('color-warm', f.preset_hash, f.target)


def acknowledge_payload(review):
    return {key: deepcopy(review[key]) for key in ('review_id', 'review_sha256', 'target', 'preset_id', 'preset_sha256')} | {
        'before_sha256': review['before']['sha256'], 'after_sha256': review['after']['sha256'], 'accepted': True}


def read_side(f, review, side):
    chunks = []
    metadata = review[side]
    for page in range(metadata['page_count']):
        item = f.owner.retrieve(review['review_id'], review['review_sha256'], f.target,
                                side, metadata['sha256'], page)
        raw = b64decode(item['base64'], validate=True)
        assert sha256(raw).hexdigest() == item['page_sha256']
        assert item['offset'] == page * R.PAGE_BYTES
        assert len(raw) == item['page_byte_length'] <= R.PAGE_BYTES
        assert item['sha256'] == metadata['sha256'] and item['byte_length'] == metadata['byte_length']
        chunks.append(raw)
    result = b''.join(chunks)
    assert len(result) == metadata['byte_length'] and sha256(result).hexdigest() == metadata['sha256']
    return result


def approve(f, review):
    read_side(f, review, 'before'); read_side(f, review, 'after')
    return f.owner.acknowledge(acknowledge_payload(review))


def test_builtin_warm_uses_existing_complete_candidate_and_preserves_unselected_values(fixture):
    f = fixture
    before = deepcopy(f.engine.state)
    preset = C.resolve('color-warm', f.preset_hash)
    candidate = R._candidate(f.engine.state, preset)
    assert candidate == SC.apply_modules(f.engine.state, preset['modules'])
    assert candidate['_exposure'] == (0.3, 250., 0.05, *before['_exposure'][3:])
    assert candidate['_exposure_ref_k'] == before['_exposure_ref_k']
    assert candidate['_retained_other_effect'] is f.engine.state['_retained_other_effect']
    assert candidate['_repair_ops'] is f.engine.state['_repair_ops']
    review = prepare(f)
    assert len(f.engine.render_calls) == 2
    assert f.engine.render_calls[0][0] == before
    assert f.engine.render_calls[1][0] == candidate
    assert f.engine.state == before
    assert review['before']['sha256'] != review['after']['sha256']
    assert review['approval_only'] is True and review['runtime_verified'] is False
    assert review['module_ids'] == sorted(preset['modules'])
    assert f.owner._reviews[review['review_id']]['approval'] is None
    assert not {'before_state', 'candidate_state', 'history', 'people_graph'} & set(review)


def test_all_unsupported_modules_reject_the_whole_saved_preset(fixture, monkeypatch):
    f = fixture
    preset = C.resolve('color-warm', f.preset_hash)
    preset['modules']['lnx.blemish.v1'] = {'strength': 0.0}
    monkeypatch.setattr(C, 'resolve', lambda *_: preset)
    with pytest.raises(ValueError, match='complete saved preset is rejected'):
        prepare(f)
    assert f.engine.render_calls == [] and not f.owner._reviews


def test_xmp_provenance_is_never_invented_stripped_or_acknowledged(fixture, monkeypatch):
    preset = C.resolve('color-warm', fixture.preset_hash)
    preset['xmp_import'] = {'source_sha256': 'a' * 64}
    monkeypatch.setattr(C, 'resolve', lambda *_: preset)
    with pytest.raises(ValueError, match='xmp_requires_dedicated_review'):
        prepare(fixture)
    assert not fixture.engine.render_calls


def test_retained_decoration_keeps_its_separate_review_boundary(fixture):
    fixture.engine.state['_face_decoration_preset_retained_active'] = True
    with pytest.raises(ValueError, match='dedicated complete preset review'):
        prepare(fixture)
    assert not fixture.engine.render_calls


def test_paged_bytes_are_exact_immutable_pngs_and_both_complete_images_are_required(fixture):
    f = fixture; review = prepare(f)
    assert review['before']['page_count'] > 1 and review['after']['page_count'] > 1
    with pytest.raises(ValueError, match='every page'):
        f.owner.acknowledge(acknowledge_payload(review))
    before = read_side(f, review, 'before')
    assert before.startswith(b'\x89PNG\r\n\x1a\n')
    with pytest.raises(ValueError, match='every page'):
        f.owner.acknowledge(acknowledge_payload(review))
    after = read_side(f, review, 'after')
    assert before != after
    receipt = f.owner.acknowledge(acknowledge_payload(review))
    assert receipt['schema'] == R.APPROVAL_SCHEMA and receipt['approval_only'] is True
    assert f.owner.acknowledge(acknowledge_payload(review)) == receipt
    assert len(f.engine.render_calls) == 2  # Image reads/ACK never render or apply again.


@pytest.mark.parametrize('field,value', [('accepted', False), ('accepted', 1), ('before_sha256', 'a' * 64),
                                       ('after_sha256', 'b' * 64), ('preset_id', 'portrait-soft')])
def test_ack_cannot_change_exact_pair_or_be_implicit(fixture, field, value):
    review = prepare(fixture); approve(fixture, review)
    ack = {**acknowledge_payload(review), field: value}
    with pytest.raises(ValueError):
        fixture.owner.acknowledge(ack)


@pytest.mark.parametrize('page', [-1, 100000, True, 0.0, '0'])
def test_page_index_cannot_escape_fixed_byte_ranges(fixture, page):
    f = fixture; review = prepare(f)
    with pytest.raises(ValueError):
        f.owner.retrieve(review['review_id'], review['review_sha256'], f.target, 'before', review['before']['sha256'], page)


@pytest.mark.parametrize('mutation', ['state', 'snapshot', 'source', 'load', 'revision', 'row', 'people', 'context', 'workspace'])
def test_each_exact_target_fence_invalidates_review_and_approval(fixture, mutation):
    f = fixture; review = prepare(f); receipt = approve(f, review)
    if mutation == 'state': f.engine.state['_retained_other_effect']['amount'] = 0.8
    elif mutation == 'snapshot': f.engine.unrelated_snapshot_input = 'changed'
    elif mutation == 'source': f.path.write_bytes(f.path.read_bytes() + b'changed')
    elif mutation == 'load': f.engine._load_id = 'new-load'
    elif mutation == 'revision': f.engine._document_version_owner.advance(f.engine._docs[0])
    elif mutation == 'row': f.engine._docs[0] = dict(f.engine._docs[0])
    elif mutation == 'people': f.engine._people_graph_owner.fence += 1
    elif mutation == 'context': f.engine._people_active_context = dict(f.engine._people_active_context)
    else: f.engine._document_version_owner.new_workspace()
    with pytest.raises(ValueError):
        f.owner.retrieve(review['review_id'], review['review_sha256'], f.target, 'before', review['before']['sha256'], 0)
    with pytest.raises(ValueError):
        f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    assert not f.owner._reviews[review['review_id']]['consumed']


def test_missing_runtime_fence_is_not_initialised_by_read(fixture):
    f = fixture; row = f.engine._docs[0]
    del row[DV.KEY]
    with pytest.raises(ValueError, match='cannot initialise'):
        prepare(f)
    assert DV.KEY not in row


def test_changed_source_before_first_review_cannot_authorize_loaded_old_pixels(fixture):
    fixture.path.write_bytes(fixture.path.read_bytes() + b'changed since decode')
    with pytest.raises(ValueError, match='changed after its actual load'):
        prepare(fixture)
    assert not fixture.engine.render_calls and not fixture.owner._reviews


def test_unopened_people_owner_is_not_activated_by_review(fixture):
    f = fixture; f.engine._people_active_context = None
    with pytest.raises(ValueError, match='existing active document owner'):
        prepare(f)
    assert f.engine._people_active_context is None and not f.engine.render_calls


def test_changed_or_missing_saved_recipe_blocks_old_images_and_approval(fixture, monkeypatch):
    f = fixture; review = prepare(f); receipt = approve(f, review)
    def unavailable(*_):
        raise ValueError('saved preset changed')
    monkeypatch.setattr(C, 'resolve', unavailable)
    with pytest.raises(ValueError, match='saved preset changed'):
        f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)


def test_authority_is_one_shot_and_does_not_dispatch_replay_or_clone_history(fixture):
    f = fixture; review = prepare(f); before = deepcopy(f.engine.state)
    receipt = approve(f, review)
    authority = f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    assert authority['preset_command'] == {'cmd': 'preset', 'action': 'apply', 'id': 'color-warm',
                                           'document_id': f.target['load_id']}
    assert authority['target']['document_id'] != authority['preset_command']['document_id']
    assert f.engine.state == before and len(f.engine.render_calls) == 2
    assert f.engine._docs[0]['document_revision'] == 0 and f.owner._bytes == 0
    with pytest.raises(ValueError, match='already consumed'):
        f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    with pytest.raises(ValueError):
        f.owner.acknowledge(acknowledge_payload(review))


def test_forged_receipt_and_unacknowledged_review_never_authorize(fixture):
    f = fixture; review = prepare(f)
    with pytest.raises(ValueError, match='forged'):
        f.owner.consume(acknowledge_payload(review), f.target, 'color-warm', f.preset_hash)
    receipt = approve(f, review)
    forged = {**receipt, 'approval_id': 'forged'}
    with pytest.raises(ValueError, match='forged'):
        f.owner.consume(forged, f.target, 'color-warm', f.preset_hash)


def test_expiry_restart_and_lost_bytes_fail_closed_without_recreating_review(fixture):
    f = fixture; review = prepare(f); receipt = approve(f, review)
    restarted = R.WorkflowPresetReviews(f.engine, clock=lambda: f.now[0])
    with pytest.raises(ValueError, match='missing or expired'):
        restarted.consume(receipt, f.target, 'color-warm', f.preset_hash)
    record = f.owner._reviews[review['review_id']]
    record['images']['after'] = record['images']['after'][:-1] + b'!'
    with pytest.raises(ValueError, match='lost or changed'):
        f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    f.now[0] += R.TTL
    with pytest.raises(ValueError, match='missing or expired'):
        f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    assert f.owner._bytes == 0 and not f.owner._reviews and len(f.engine.render_calls) == 2


def test_inputs_changing_during_either_render_never_retain_an_approval(fixture, monkeypatch):
    f = fixture
    def changed(*args, **kwargs):
        result = f.renderer(*args, **kwargs)
        f.engine.state['_retained_other_effect']['amount'] += 0.1
        return result
    monkeypatch.setattr(FULL, 'render', changed)
    with pytest.raises(ValueError, match='changed'):
        prepare(f)
    assert f.owner._bytes == 0 and not f.owner._reviews


def test_cancellation_and_full_renderer_failure_have_no_proxy_fallback(fixture, monkeypatch):
    f = fixture
    with pytest.raises(InterruptedError):
        f.owner.prepare('color-warm', f.preset_hash, f.target, cancelled=lambda: True)
    assert not f.engine.render_calls
    def unavailable(*_args, **_kwargs):
        raise ValueError('original full source unavailable')
    monkeypatch.setattr(FULL, 'render', unavailable)
    with pytest.raises(ValueError, match='original full source unavailable'):
        prepare(f)
    assert f.owner._bytes == 0 and not f.owner._reviews


def test_invalid_renderer_digest_is_not_image_evidence(fixture, monkeypatch):
    actual = DISPLAY.image
    def wrong(*args, **kwargs):
        compact, display, proof = actual(*args, **kwargs)
        compact['sha256'] = display['sha256'] = '0' * 64
        return compact, display, proof
    monkeypatch.setattr(DISPLAY, 'image', wrong)
    with pytest.raises(ValueError, match='PNG bytes differ'):
        prepare(fixture)
    assert not fixture.owner._reviews


def test_cache_limits_refuse_without_evicting_existing_approved_evidence(fixture, monkeypatch):
    f = fixture; first = prepare(f); receipt = approve(f, first)
    monkeypatch.setattr(R, 'MAX_ACTIVE_REVIEWS', 1)
    with pytest.raises(ValueError, match='not silently evicted'):
        prepare(f)
    assert f.owner.consume(receipt, f.target, 'color-warm', f.preset_hash)
    monkeypatch.setattr(R, 'MAX_REVIEWS', 1)
    with pytest.raises(ValueError, match='not silently evicted'):
        prepare(f)


def test_image_budget_does_not_silently_lower_resolution(fixture, monkeypatch):
    monkeypatch.setattr(R, 'MAX_CACHE_BYTES', 1)
    with pytest.raises(ValueError, match='no resolution or image detail was reduced'):
        prepare(fixture)
    assert not fixture.owner._reviews and fixture.owner._bytes == 0


def test_public_return_values_cannot_mutate_retained_authority(fixture):
    f = fixture; review = prepare(f); exact = deepcopy(review)
    review['before']['sha256'] = 'b' * 64
    receipt = approve(f, exact); genuine = deepcopy(receipt)
    receipt['target']['load_id'] = 'changed'
    assert f.owner.consume(genuine, f.target, 'color-warm', f.preset_hash)['target'] == f.target


@pytest.mark.parametrize('target', [{}, {'document_id': 'a', 'load_id': 'b', 'revision': '01'},
                                   {'document_id': 'a', 'load_id': 'b', 'revision': 0},
                                   {'document_id': 'a', 'load_id': 'b', 'revision': str(2**64)}])
def test_target_schema_is_exact_and_never_substitutes_load_id_for_revision(target):
    with pytest.raises(ValueError):
        R.check_target(target)
