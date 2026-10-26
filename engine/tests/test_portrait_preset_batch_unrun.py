"""Authored UNRUN: prepared-original group protocol/claim boundary fixtures.

No acceptance claim: actual rendering, MediaPipe, native bridge, history reload,
GUI presentation, build, image quality and performance require separate runs.
"""
from types import SimpleNamespace
from copy import deepcopy
import pytest
from lumaretouch_engine import portrait_preset_batch as G


def request(action, **kw):
    return {'cmd': 'batch', 'action': action, 'request_id': 'request-1', **kw}


def target():
    return {'document_id': 'target-1', 'revision': '4', 'review_sha256': 'c' * 64,
            'before': {'sha256': 'a' * 64}, 'after': {'sha256': 'b' * 64}}


def test_read_only_classifier_never_admits_commit_or_extra_options():
    p = request('portrait_preset_catalogue')
    assert G.read_only(p)
    assert not G.read_only({**p, 'accepted': True})
    assert not G.read_only(request('portrait_preset_commit', preflight_token='a' * 32,
                                  portrait_preset_ack=[], accepted=True))
    assert not G.read_only({'cmd': 'batch', 'action': 'portrait_preset_catalogue'})


def test_preflight_requires_bounded_exact_stable_target_set():
    p = request('portrait_preset_preflight', docs=['target-1'], preset_id='preset-1', preset_sha256='a' * 64)
    assert G.read_only(p)
    for docs in ([], ['target-1', 'target-1'], [1], ['x'] * 9):
        assert not G.read_only({**p, 'docs': docs})
    assert not G.read_only({**p, 'preset_sha256': 'a' * 63})


def test_image_page_cannot_use_boolean_negative_or_out_of_bound_page():
    p = request('portrait_preset_image', preflight_token='a' * 32, document_id='target-1', side='before', page=0)
    assert G.read_only(p)
    for page in (-1, True, 64):
        assert not G.read_only({**p, 'page': page})
    assert not G.read_only({**p, 'side': 'mask'})


def test_group_ack_binds_document_revision_review_and_both_complete_images():
    row = target(); ack = G.acknowledgment(row)
    assert ack == {'document_id': 'target-1', 'revision': '4', 'review_sha256': 'c' * 64,
                   'before_sha256': 'a' * 64, 'after_sha256': 'b' * 64}
    altered = deepcopy(row); altered['after']['sha256'] = 'd' * 64
    assert G.acknowledgment(altered) != ack


def test_parked_lookup_never_accepts_current_or_duplicate_identity():
    engine = SimpleNamespace(_docs=[{'document_id': 'current'}, {'document_id': 'target'}], _doc_index=0)
    owner = G.PortraitPresetBatch(engine, None)
    assert owner._row('target')[0] == 1
    with pytest.raises(ValueError, match='parked'): owner._row('current')
    engine._docs.append({'document_id': 'target'})
    with pytest.raises(ValueError, match='parked'): owner._row('target')


def test_generic_and_foreign_completed_tokens_are_not_group_authority():
    store = SimpleNamespace(completed=lambda token, workspace: {'success': True})
    batch = SimpleNamespace(preflight=SimpleNamespace(store=store), versions=SimpleNamespace(workspace='workspace'))
    owner = G.PortraitPresetBatch(None, batch)
    assert not owner.owns('a' * 32)
    store.completed = lambda token, workspace: {'portrait_preset': True, 'success': False, 'outcome_unknown': True}
    assert owner.owns('a' * 32)


def test_terminal_retry_requires_original_group_acceptance():
    ack = [G.acknowledgment(target())]
    cached = {'portrait_preset': True, 'portrait_preset_ack': ack, 'outcome_unknown': True, 'success': False}
    store = SimpleNamespace(completed=lambda *_: cached)
    batch = SimpleNamespace(preflight=SimpleNamespace(store=store), versions=SimpleNamespace(workspace='workspace'))
    owner = G.PortraitPresetBatch(None, batch)
    p = request('portrait_preset_commit', preflight_token='a' * 32, portrait_preset_ack=ack, accepted=True)
    assert owner._commit(p)['replayed'] is True
    assert owner._commit(p)['outcome_unknown'] is True
    for changed in ({'accepted': False}, {'portrait_preset_ack': []}):
        with pytest.raises(ValueError, match='original acceptance'): owner._commit({**p, **changed})


def test_unprepared_target_refusal_precedes_fresh_state_or_analysis():
    # Missing fresh-state/analysis methods prove this refusal cannot start work.
    engine = SimpleNamespace()
    with pytest.raises(ValueError, match='unedited original'):
        G._admit(engine, {'copy_number': 1}, {})


def commit_fixture():
    raw = b'not-a-real-render-test-transport-only'
    item = target()
    for side in ('before', 'after'):
        item[side] = {'sha256': G.sha256(raw).hexdigest(), 'page_count': 1}
    token = 'a' * 32
    t = SimpleNamespace(index=1, path='/target')
    plan = SimpleNamespace(token=token, targets=[t], modules=('lnx.skin.v1',), source_id='target-1',
                           source_revision=4, source_path='/target', params=lambda: {'lnx.skin.v1': {}})
    log = []
    store = SimpleNamespace(completed=lambda *_: None, get=lambda *_: plan,
                            claim=lambda *a, **kw: log.append('claim'),
                            finish=lambda p, result: log.append(deepcopy(result)))
    batch = SimpleNamespace(preflight=SimpleNamespace(store=store), versions=SimpleNamespace(workspace='workspace'))
    owner = G.PortraitPresetBatch(None, batch)
    owner.records[token] = {'targets': [item], 'images': {'target-1': {'before': raw, 'after': raw}},
        'served': {'target-1': {'before': {0}, 'after': {0}}},
        'inputs': [{'before': {'render': {'source_proof': {'frozen': True}}}}],
        'preset_id': 'preset-1', 'preset_sha256': 'b' * 64, 'mode': 'legacy_scalar'}
    owner._verify = lambda *args: log.append('verify')
    p = request('portrait_preset_commit', preflight_token=token,
                portrait_preset_ack=[G.acknowledgment(item)], accepted=True)
    return owner, batch, log, p


def test_every_page_is_required_before_claim_even_with_exact_ack():
    owner, batch, log, p = commit_fixture()
    owner.records[p['preflight_token']]['served']['target-1']['after'].clear()
    with pytest.raises(ValueError, match='every page'): owner._commit(p)
    assert 'claim' not in log


def test_publication_failure_consumes_token_and_remains_unknown_not_no_write():
    owner, batch, log, p = commit_fixture()
    def fail(*args, **kw):
        assert 'claim' in log
        assert callable(kw['before_publish'])
        raise ValueError('uncertain canonical batch publication')
    batch.commit = fail
    result = owner._commit(p)
    assert result['success'] is False and result['outcome_unknown'] is True
    assert result['portrait_preset_ack'] == p['portrait_preset_ack']
    assert 'no_write' not in result
    assert owner.records[p['preflight_token']]['images'] == {}
    assert log[-1]['outcome_unknown'] is True
