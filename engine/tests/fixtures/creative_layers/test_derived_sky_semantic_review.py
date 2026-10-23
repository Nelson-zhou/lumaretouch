"""AUTHORED / UNRUN: canonical sky proposal review and exact replay ownership.

Synthetic worker output exercises transport/proof fences only. These fixtures
do not establish OneFormer quality, model installation, native mask composition,
GPU behaviour, photographic acceptance, export codecs or end-to-end UI results.
"""
from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace
import base64
import io

import numpy as np
from PIL import Image
import pytest

from lumaretouch_engine.sky_semantic import controller as C
from lumaretouch_engine.sky_semantic import immutable_input as I
from lumaretouch_engine.sky_semantic import job as J
from lumaretouch_engine.sky_semantic import manifest as M
from lumaretouch_engine.sky_semantic import resolver as R
from lumaretouch_engine.sky_semantic import review as V
from lumaretouch_engine.sky_semantic import state as S


SOURCE = {'sha256': 'a' * 64, 'width': 1024, 'height': 2}
HOST = {name: 'fixture-only' for name in ('python', 'torch', 'torchvision', 'numpy', 'Pillow')}


def packet(value=.4, source=None):
    source = deepcopy(SOURCE if source is None else source)
    return I.build(np.full((source['height'], source['width'], 3), value, np.float32), source)


def png(pixels):
    output = io.BytesIO()
    Image.fromarray(pixels).save(output, format='PNG')
    return base64.b64encode(output.getvalue()).decode('ascii')


def result_for(owned, *, original=False):
    width, height = owned['input_size']
    labels = np.zeros((height, width), np.uint8)
    labels[:, :width // 2] = 255
    support = np.full(labels.shape, 200, np.uint8)
    overlay = np.full((*labels.shape, 4), 255, np.uint8)
    overlay[..., 3] = labels
    result = {
        'source': deepcopy(owned['source']), 'model': M.identity(), 'host': deepcopy(HOST),
        'device': 'cpu', 'input_size': list(owned['input_size']), 'input_sha256': owned['input_sha256'],
        'source_image': 'data:image/png;base64,' + png(I.array(owned)),
        'fields_sha256': {key: sha256(labels.tobytes() + support.tobytes()).hexdigest() for key in S.REGIONS},
        '_fields': {key: {'labels': png(labels), 'support': png(support)} for key in S.REGIONS},
        'counts': {key: int((labels > 0).sum()) for key in S.REGIONS},
        'candidate_overlays': {key: 'data:image/png;base64,' + png(overlay) for key in S.REGIONS},
        'proposal_only': True, 'review_required': True, 'horizon_automatic': False,
        'confidence_note': 'Fixture only, not a quality claim.',
    }
    if not original:
        result['_immutable_input'] = I.metadata(owned)
    return result


def fake_jobs(monkeypatch, result, *, on_poll=None, running=False):
    launched = []

    class Job:
        def __init__(self, path, source, device, *, immutable_input=None):
            self.path, self.source, self.device = path, deepcopy(source), device
            self.immutable_input = deepcopy(immutable_input)
            self.state, self.error, self.result = 'running', None, deepcopy(result)
            self.cancelled = False
            launched.append(self)

        def poll(self):
            if on_poll is not None:
                on_poll()
            self.state = 'running' if running else 'ready'
            return self.state

        def cancel(self):
            self.cancelled = True
            self.state, self.result = 'cancelled', None

    monkeypatch.setattr(V, 'SemanticJob', Job)
    monkeypatch.setattr(J, 'SemanticJob', Job)
    return launched


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    R._CACHE.clear()
    monkeypatch.setattr(M, 'installation_stamp', lambda: ('fixture-installation',))
    yield
    R._CACHE.clear()


@pytest.fixture
def installed(monkeypatch, tmp_path):
    (tmp_path / 'receipt.json').write_text('{}')
    monkeypatch.setattr(M, 'directory', lambda: tmp_path)
    return tmp_path


def owned_review(monkeypatch, *, original=False):
    owned = packet()
    result = result_for(owned, original=original)
    launched = fake_jobs(monkeypatch, result)
    live = {'path': '/physical/original.tiff' if original else None,
            'source': deepcopy(SOURCE), 'packet': None if original else owned, 'revision': 1}
    events = []
    owner = V.SemanticReview(lambda: ('document', live['revision']), events.append,
        lambda: (live['path'], live['source'], live['packet']))
    started = owner.start(live['path'], live['source'], 'cpu', immutable_input=live['packet'])
    return owner, started['proposal_id'], live, events, launched


def test_derived_proposal_uses_owned_canonical_packet_and_returns_only_draft(monkeypatch):
    owner, proposal, live, events, launched = owned_review(monkeypatch)
    assert launched[0].path is None
    assert launched[0].immutable_input == live['packet']
    owner.tick()
    assert events[-1]['state'] == 'ready'
    assert '_immutable_input' not in events[-1] and '_fields' not in events[-1]
    with pytest.raises(ValueError):
        owner.accept(proposal, {'sky': .5})
    owner.acknowledge(proposal, 'sky')
    accepted = owner.accept(proposal, {'sky': .5})
    assert accepted['semantic']['source'] == SOURCE
    assert accepted['semantic']['input_sha256'] == live['packet']['input_sha256']
    assert accepted['semantic']['regions'] == {'sky': .5}
    assert accepted['draft_only'] and accepted['requires_sky_output_review']
    assert accepted['person_declaration_unchanged'] and accepted['horizon_unchanged']
    assert 'pixels' not in accepted['semantic'] and '_fields' not in accepted['semantic']


def test_original_proposal_keeps_existing_real_path_route(monkeypatch):
    owner, proposal, live, events, launched = owned_review(monkeypatch, original=True)
    assert launched[0].path == live['path'] and launched[0].immutable_input is None
    owner.tick()
    owner.acknowledge(proposal, 'sky')
    assert owner.accept(proposal, {'sky': .5})['semantic']['source'] == SOURCE
    assert events[-1]['state'] == 'ready'


@pytest.mark.parametrize('boundary', ['ready', 'shown', 'accept'])
def test_source_input_is_rechecked_at_every_review_boundary(monkeypatch, boundary):
    owner, proposal, live, events, _ = owned_review(monkeypatch)
    if boundary != 'ready':
        owner.tick()
    if boundary == 'accept':
        owner.acknowledge(proposal, 'sky')
    live['packet'] = packet(.8)
    if boundary == 'ready':
        owner.tick()
        assert events[-1]['state'] == 'failed' and owner.result is None
        assert not any(event['state'] == 'ready' for event in events)
    else:
        with pytest.raises(ValueError):
            if boundary == 'shown':
                owner.acknowledge(proposal, 'sky')
            else:
                owner.accept(proposal, {'sky': .5})


@pytest.mark.parametrize('change', ['source', 'canonical', 'pixel_bytes', 'path', 'revision'])
def test_changed_source_or_packet_cannot_reuse_shown_proposal(monkeypatch, change):
    owner, proposal, live, _, _ = owned_review(monkeypatch)
    owner.tick()
    owner.acknowledge(proposal, 'sky')
    if change == 'source':
        live['source'] = {**SOURCE, 'sha256': 'b' * 64}
    elif change == 'canonical':
        live['packet'] = {**live['packet'], 'canonical_sha256': 'c' * 64}
    elif change == 'pixel_bytes':
        live['packet'] = {**live['packet'], 'pixels': bytes(len(live['packet']['pixels']))}
    elif change == 'path':
        live['path'] = '/physical/original.tiff'
    else:
        live['revision'] += 1
    with pytest.raises(ValueError):
        owner.accept(proposal, {'sky': .5})


@pytest.mark.parametrize('field', ['source', 'host', '_fields', 'candidate_overlays', 'counts', 'source_image'])
def test_actual_review_payload_cannot_be_changed_after_ready(monkeypatch, field):
    owner, proposal, _, _, _ = owned_review(monkeypatch)
    owner.tick()
    if field == 'source':
        owner.result[field]['sha256'] = 'b' * 64
    elif field == 'host':
        owner.result[field]['torch'] = 'changed'
    elif field == '_fields':
        owner.result[field]['sky']['labels'] = owner.result[field]['sky']['support']
    elif field == 'candidate_overlays':
        owner.result[field]['sky'] = 'changed-overlay'
    elif field == 'counts':
        owner.result[field]['sky'] += 1
    else:
        owner.result[field] = 'changed-locator'
    with pytest.raises(ValueError):
        owner.acknowledge(proposal, 'sky')


@pytest.mark.parametrize('boundary', ['ready', 'remember'])
@pytest.mark.parametrize('change', ['count', 'count_type', 'alpha', 'rgb', 'mode', 'size', 'missing', 'oversized'])
def test_initial_display_must_match_the_exact_decoded_labels(monkeypatch, boundary, change):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    if change == 'count':
        result['counts']['sky'] += 1
    elif change == 'count_type':
        result['counts']['sky'] = True
    elif change == 'missing':
        del result['candidate_overlays']['water']
    elif change == 'oversized':
        limit = 4 * M.MAX_MASK_PIXELS + 65536
        result['candidate_overlays']['sky'] = 'data:image/png;base64,' + 'A' * (4 * ((limit + 2) // 3) + 4)
    else:
        width, height = owned['input_size']
        overlay = np.full((height, width, 4), 255, np.uint8)
        overlay[:, width // 2:, 3] = 0
        if change == 'alpha':
            overlay[0, 0, 3] = 0
        elif change == 'rgb':
            overlay[0, 0, 0] = 0
        elif change == 'mode':
            overlay = overlay[..., :3]
        else:
            overlay = overlay[:, :-1]
        result['candidate_overlays']['sky'] = 'data:image/png;base64,' + png(overlay)
    if boundary == 'remember':
        with pytest.raises(ValueError):
            R.remember(descriptor, result, immutable_input=owned)
        assert not R._CACHE
    else:
        fake_jobs(monkeypatch, result)
        events = []
        owner = V.SemanticReview(lambda: ('document', 1), events.append, lambda: (None, SOURCE, owned))
        owner.start(None, SOURCE, 'cpu', immutable_input=owned)
        owner.tick()
        assert events[-1]['state'] == 'failed' and owner.result is None
        assert not any(event['state'] == 'ready' for event in events)


def test_emitted_payload_and_caller_packet_do_not_alias_owned_review(monkeypatch):
    owner, proposal, live, events, launched = owned_review(monkeypatch)
    owner.tick()
    events[-1]['counts']['sky'] = 0
    events[-1]['source']['sha256'] = 'b' * 64
    launched[0].result['counts']['sky'] = 0
    assert owner.result['counts']['sky'] > 0 and owner.result['source'] == SOURCE
    owner.acknowledge(proposal, 'sky')
    assert owner.accept(proposal, {'sky': .5})['semantic']['source'] == SOURCE
    live['packet']['source']['sha256'] = 'd' * 64
    assert owner.immutable_input['source'] == SOURCE


def test_controller_selects_canonical_owner_instead_of_original_or_proxy(monkeypatch):
    from lumaretouch_engine import creative_derived_source as D, creative_derived_sky as K
    from lumaretouch_engine import sky_replacement_preview as P
    owned = packet()
    launched = fake_jobs(monkeypatch, result_for(owned))
    session = {'path': '/must-not-read/original.tiff', 'binding': deepcopy(SOURCE), 'shown': True}
    monkeypatch.setattr(P, 'controller', lambda engine, emit: SimpleNamespace(matching=lambda command: session))
    monkeypatch.setattr(P, 'context', lambda engine: ('document', 1))
    monkeypatch.setattr(D, 'record', lambda engine: {'id': 'effective-source'})
    captures = []
    monkeypatch.setattr(K, 'semantic_input', lambda engine: captures.append(engine) or deepcopy(owned))
    engine = SimpleNamespace(_guard_editable=lambda reason: None)
    events = []
    owner = C.SemanticController(engine, events.append)
    owner.handle({'cmd': 'sky_semantic', 'action': 'start', 'request_id': '1' * 32,
                  'document_id': 'document', 'session_id': '2' * 32, 'run_id': '1' * 32, 'device': 'cpu'})
    assert events[-1]['success'] and len(launched) == 1 and captures
    assert launched[0].path is None and launched[0].immutable_input == owned
    owner.owner.tick()
    old_proposal = owner.owner.proposal
    owner.owner.acknowledge(old_proposal, 'sky')

    def unavailable(engine):
        raise ValueError('Canonical source capture failed')

    monkeypatch.setattr(K, 'semantic_input', unavailable)
    owner.handle({'cmd': 'sky_semantic', 'action': 'start', 'request_id': '3' * 32,
                  'document_id': 'document', 'session_id': '2' * 32, 'run_id': '3' * 32, 'device': 'cpu'})
    assert not events[-1]['success']
    assert owner.owner.proposal is None and owner.owner.result is None and not owner.owner.shown
    owner.handle({'cmd': 'sky_semantic', 'action': 'accept', 'request_id': 'accept-old',
                  'document_id': 'document', 'session_id': '2' * 32, 'run_id': '3' * 32,
                  'proposal_id': old_proposal, 'regions': {'sky': .5}})
    assert not events[-1]['success'] and len(launched) == 1


def test_remember_checks_exact_source_not_only_identical_field_hashes():
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    changed = deepcopy(result)
    changed['source']['sha256'] = 'b' * 64
    with pytest.raises(ValueError):
        R.remember(descriptor, changed, immutable_input=owned)
    assert not R._CACHE


def test_derived_cache_hit_never_opens_physical_original(monkeypatch, installed):
    from lumaretouch_engine import local_mask_state as L
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    expected = R.remember(descriptor, result, immutable_input=owned)

    def forbidden(*args, **kwargs):
        raise AssertionError('Derived inference must not reopen the physical original or rerun on a cache hit')

    monkeypatch.setattr(L, 'file_stamp', forbidden)
    monkeypatch.setattr(L, 'source_digest', forbidden)
    monkeypatch.setattr(J, 'SemanticJob', forbidden)
    assert R.resolve(descriptor, None, immutable_input=owned) is expected
    with pytest.raises(ValueError):
        R.resolve(descriptor, '/original.tiff', immutable_input=owned)
    with pytest.raises(ValueError):
        R.resolve(descriptor, None)


@pytest.mark.parametrize('change', ['source', 'pixels', 'canonical', 'model', 'fields'])
def test_cache_hit_rechecks_packet_descriptor_model_and_actual_fields(monkeypatch, installed, change):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    fields = R.remember(descriptor, result, immutable_input=owned)
    if change == 'source':
        owned = packet(source={**SOURCE, 'sha256': 'b' * 64})
    elif change == 'pixels':
        owned = packet(.8)
    elif change == 'canonical':
        owned['canonical_sha256'] = 'c' * 64
    elif change == 'model':
        descriptor['model']['adapter_sha256'] = 'd' * 64
    else:
        labels = fields['sky'][0]
        labels.flags.writeable = True
        labels[0, 0] = 0
    with pytest.raises(ValueError):
        R.resolve(descriptor, None, immutable_input=owned)


def test_cache_hit_does_not_hide_removed_installation(installed):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    R.remember(descriptor, result, immutable_input=owned)
    (installed / 'receipt.json').unlink()
    with pytest.raises(ValueError):
        R.resolve(descriptor, None, immutable_input=owned)


def test_strict_replay_uses_new_worker_even_after_successful_review(monkeypatch, installed):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    R.remember(descriptor, result, immutable_input=owned)
    launched = fake_jobs(monkeypatch, result)
    fields = R.resolve(descriptor, None, immutable_input=owned, force=True)
    assert set(fields) == set(S.REGIONS) and len(launched) == 1
    assert launched[0].path is None and launched[0].immutable_input == owned


@pytest.mark.parametrize('change', ['source', 'host', 'device', 'model', 'input_sha256',
                                  'input_size', 'fields_sha256', '_fields', '_immutable_input'])
def test_strict_replay_rejects_changed_worker_identity_or_field_bytes(monkeypatch, installed, change):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    changed = deepcopy(result)
    if change == 'source':
        changed['source']['sha256'] = 'b' * 64
    elif change == 'host':
        changed['host']['torch'] = 'different-runtime'
    elif change == 'device':
        changed['device'] = 'cuda'
    elif change == 'model':
        changed['model']['adapter_sha256'] = 'c' * 64
    elif change == 'input_sha256':
        changed['input_sha256'] = 'd' * 64
    elif change == 'input_size':
        changed['input_size'][0] -= 1
    elif change == 'fields_sha256':
        changed['fields_sha256']['sky'] = 'e' * 64
    elif change == '_fields':
        changed['_fields']['sky']['labels'] = changed['_fields']['sky']['support']
    else:
        changed['_immutable_input']['canonical_sha256'] = 'f' * 64
    launched = fake_jobs(monkeypatch, changed)
    with pytest.raises(ValueError):
        R.resolve(descriptor, None, immutable_input=owned, force=True)
    assert len(launched) == 1 and not R._CACHE


def test_replay_input_mutation_and_cancellation_never_return_or_cache_fields(monkeypatch, installed):
    owned = packet()
    result = result_for(owned)
    descriptor = S.accept(result, SOURCE, {'sky': .5})
    launched = fake_jobs(monkeypatch, result,
        on_poll=lambda: owned.__setitem__('canonical_sha256', 'c' * 64))
    with pytest.raises(ValueError):
        R.resolve(descriptor, None, immutable_input=owned, force=True)
    assert len(launched) == 1 and not R._CACHE
    owned = packet()
    cancelled = [False]
    launched = fake_jobs(monkeypatch, result, on_poll=lambda: cancelled.__setitem__(0, True), running=True)
    with pytest.raises(InterruptedError):
        R.resolve(descriptor, None, immutable_input=owned, force=True, cancelled=lambda: cancelled[0])
    assert launched[0].cancelled and not R._CACHE
