"""AUTHORED / UNRUN: fabric review source ownership, not photographic acceptance.

Mocks isolate transport/fences. Actual solver, native raster, export parity and
model-driven quality still require authorized runtime testing.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_derived_recovery_contract import owned, preview
from lumaretouch_engine import creative_derived_recovery as D
from lumaretouch_engine import creative_derived_fabric as F
from lumaretouch_engine import effect_recovery_preview as V
from lumaretouch_engine import effect_recovery_state as S
from lumaretouch_engine import people_recovery as P


def fabric(monkeypatch):
    engine, _, _, source, proof, capture = owned(monkeypatch)
    context = {'version': 1, 'source': source, 'fabric_amount': .4,
               'evidence_key': ['actual-source', 'measured-clothes', 'repair-stack']}
    monkeypatch.setattr(F, 'recovery_context', lambda actual: deepcopy(context))
    engine._people_cursors = {}  # Fabric is not secretly owned by a selected face.
    return engine, source, proof, capture, context


def reviewed(proof, context):
    return {'id': '2' * 32, 'target': 'fabric_fine', 'proof': proof,
            'value': S.empty(), 'people_context': None, 'global_context': context,
            'presented': True, 'committable': True}


def test_fabric_review_never_requires_or_fabricates_face_identity(monkeypatch):
    engine, _, proof, _, _ = fabric(monkeypatch)
    def no_face(*args, **kwargs):
        raise AssertionError('global review must not request a face owner')
    monkeypatch.setattr(P, 'context', no_face)
    D.require_command(engine, 'effect_recovery_preview', preview(proof, 'fabric_fine'))
    context = D.global_context(engine, 'fabric_fine')
    assert context['target'] == 'fabric_fine' and 'face_ref' not in context
    assert 'fabric_fine' not in D.TARGETS  # Face descriptor validators stay narrow.
    record = reviewed(proof, context)
    D.assert_review(engine, record)
    record['people_context'] = {'fake': 'face'}
    with pytest.raises(ValueError):
        D.assert_review(engine, record)


@pytest.mark.parametrize('target', ['skin_smoothing', 'background_replace', 'enhance'])
def test_unadapted_consumers_remain_fenced(monkeypatch, target):
    engine, _, proof, _, _ = fabric(monkeypatch)
    with pytest.raises(ValueError):
        D.require_command(engine, 'effect_recovery_preview', preview(proof, target))


@pytest.mark.parametrize('change', ['fabric_amount', 'evidence_key', 'source'])
def test_presented_review_expires_when_real_consumer_context_changes(monkeypatch, change):
    engine, _, proof, _, context = fabric(monkeypatch)
    record = reviewed(proof, D.global_context(engine, 'fabric_fine'))
    engine._effect_recovery_preview_owner = SimpleNamespace(record=record)
    request = {**proof, 'cmd': 'effect_recovery', 'action': 'apply',
               'preview_id': record['id'], 'request_id': 'apply-fabric'}
    D.require_command(engine, 'effect_recovery', request)
    if change == 'fabric_amount':
        context[change] = .6
    elif change == 'evidence_key':
        context[change].append('different-repair-output')
    else:
        context[change] = {**context[change], 'sha256': 'f' * 64}
    with pytest.raises(ValueError):
        D.require_command(engine, 'effect_recovery', request)


def test_global_review_requires_presented_committable_receipt(monkeypatch):
    engine, _, proof, _, _ = fabric(monkeypatch)
    record = reviewed(proof, D.global_context(engine, 'fabric_fine'))
    engine._effect_recovery_preview_owner = SimpleNamespace(record=record)
    request = {**proof, 'cmd': 'effect_recovery', 'action': 'apply',
               'preview_id': record['id'], 'request_id': 'apply-fabric'}
    for key in ('presented', 'committable'):
        record[key] = False
        with pytest.raises(ValueError):
            D.require_command(engine, 'effect_recovery', request)
        record[key] = True


def test_preview_owner_rechecks_before_presentation_and_prepare(monkeypatch):
    engine, _, proof, _, context = fabric(monkeypatch)
    events = []
    owner = V.RecoveryPreview(engine, events.append)
    owner.record = reviewed(proof, D.global_context(engine, 'fabric_fine'))
    context['evidence_key'].append('new-mask-content')
    with pytest.raises(ValueError):
        owner.prepare({**proof, 'preview_id': '2' * 32})
    owner.handle({**proof, 'cmd': 'effect_recovery_preview', 'action': 'presented',
                  'preview_id': '2' * 32})
    assert owner.record is None and events[-1]['state'] == 'failed'


def test_changed_context_during_real_review_cannot_publish_receipt(monkeypatch):
    engine, _, proof, _, context = fabric(monkeypatch)
    events = []
    engine._people_sync = lambda **kwargs: None
    monkeypatch.setattr(V.R, 'prepare_stage', lambda *args: SimpleNamespace())
    monkeypatch.setattr(P, 'prepare', lambda *args: None)
    def changed_during_render(*args):
        context['fabric_amount'] = .8
        return {'before': 'actual-before', 'after': 'actual-after'}
    monkeypatch.setattr(V, 'render_review', changed_during_render)
    owner = V.RecoveryPreview(engine, events.append)
    owner.handle(preview(proof, 'fabric_fine'))
    assert owner.record is None and events[-1]['state'] == 'failed'
