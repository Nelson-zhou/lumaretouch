"""AUTHORED / UNRUN: operation-scoped target finish extent disclosure.

Synthetic records and mocked resolver/snapshot boundaries do not establish actual
body support, inference, native rendering, photographic quality or acceptance.
No product imports or fixture execution occurred during authoring.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import people_state as P, skin_finish_state as S
from lumaretouch_engine import skin_colour_transfer_review as R, skin_finish_scope as C
from lumaretouch_engine import skin_colour_body_support as BODY
from test_skin_colour_transfer_review_unrun import ASSET, SUPPORT, fixture as colour_fixture


def fixture(*, finish=False, colour=False, whitening=.2, rosiness=0.):
    graph, ref, analysis, payload, _ = colour_fixture(attached=colour)
    if finish:
        graph['faces'][ref['face_instance_id']]['local_assets'][BODY.FINISH_KIND] = {
            'owner': ref, 'kind': BODY.FINISH_KIND, 'content_sha256': SUPPORT}
    graph = P.set_override(graph, 'face', ref['face_instance_id'], S.OP, '/whitening', whitening)
    graph = P.set_override(graph, 'face', ref['face_instance_id'], S.OP, '/rosiness', rosiness)
    payload['parameters'] = [{'operation_id': S.OP, 'parameter_path': '/whitening', 'value': whitening}]
    return graph, ref, analysis, payload, {'version': 1, 'whitening': whitening, 'rosiness': rosiness}


def test_old_colour_descriptor_cannot_authorize_finish_body_scope(monkeypatch):
    graph, ref, analysis, payload, recipe = fixture(colour=True)
    monkeypatch.setattr(BODY, 'resolve', lambda *a, **kw: pytest.fail('Colour support must not resolve for finish'))
    assert R.attached(graph, ref) is True
    assert R.attached(graph, ref, family='skin_finish') is False
    result = R.describe(graph, {'donor': object()}, ref, None, analysis, recipe, family='skin_finish')
    assert result == {'face_ref': ref, 'scope': 'face-only', 'body_review_sha256': None}
    assert R.for_target(SimpleNamespace(), {'state': {}}, graph, payload, family='skin_finish')['targets'] == [result]
    assert R.for_target(None, None, graph, payload) is None


def test_finish_uses_explicit_family_and_exact_target_owned_inputs(monkeypatch):
    graph, ref, analysis, _, recipe = fixture(finish=True, colour=True)
    assets = {'target-finish': object()}; bank = {'target-body': object()}; calls = []
    def resolve(actual_graph, actual_assets, actual_ref, actual_bank, actual_analysis, *, family):
        calls.append(family)
        assert actual_graph is graph and actual_assets is assets and actual_ref == ref
        assert actual_bank is bank and actual_analysis is analysis
        return {}, SUPPORT
    monkeypatch.setattr(BODY, 'resolve', resolve)
    result = R.describe(graph, assets, ref, bank, analysis, recipe, family='skin_finish')
    assert result == {'face_ref': ref, 'scope': 'face-and-reviewed-body', 'body_review_sha256': SUPPORT}
    assert calls == ['skin_finish'] and set(result) == {'face_ref', 'scope', 'body_review_sha256'}


@pytest.mark.parametrize('missing', [False, True])
def test_attached_finish_refusal_never_falls_back_to_colour_or_face(monkeypatch, missing):
    graph, ref, analysis, _, recipe = fixture(finish=True, colour=True)
    calls = []
    def resolve(*args, family):
        calls.append(family)
        if missing: return None
        raise ValueError('Finish BodyRef/person/model review is stale')
    monkeypatch.setattr(BODY, 'resolve', resolve)
    with pytest.raises(ValueError): R.describe(graph, {}, ref, {}, analysis, recipe, family='skin_finish')
    assert calls == ['skin_finish']


def test_neutral_finish_reset_does_not_certify_stale_body_review(monkeypatch):
    graph, ref, analysis, payload, recipe = fixture(finish=True, whitening=0.)
    monkeypatch.setattr(BODY, 'resolve', lambda *a, **kw: pytest.fail('Neutral finish needs no body resolver'))
    engine = SimpleNamespace(_people_export_snapshot=lambda *a, **kw: pytest.fail('Neutral finish needs no body snapshot'))
    assert R.describe(graph, {}, ref, None, analysis, recipe, family='skin_finish') == {
        'face_ref': ref, 'scope': 'neutral-no-effect', 'body_review_sha256': None}
    assert R.for_target(engine, {'state': {}}, graph, payload, family='skin_finish')['targets'][0]['scope'] == 'neutral-no-effect'


def test_partial_zero_transfer_still_discloses_remaining_target_rosiness():
    graph, ref, _, payload, _ = fixture(whitening=0., rosiness=.4)
    result = R.for_target(SimpleNamespace(), {'state': {}}, graph, payload, family='skin_finish')
    assert result == {'version': 1, 'support_transfer': 'none', 'targets': [
        {'face_ref': ref, 'scope': 'face-only', 'body_review_sha256': None}]}
    assert payload['parameters'] == [{'operation_id': S.OP, 'parameter_path': '/whitening', 'value': 0.}]


def target_snapshot(monkeypatch, *, bad=None):
    graph, ref, analysis, payload, _ = fixture(finish=True)
    row = {'path': '/target-owned.png', 'state': {'target-state': 'parked independent document'}}
    context = {'people_support_assets': {'target-support': 'owned'}}
    bank = {'target-body': 'owned'}; calls = []
    from lumaretouch_engine import full_candidate_render as FULL, body_pose_project as PROJECT
    monkeypatch.setattr(FULL, 'people_context', lambda engine, actual_row:
        context if actual_row is row else pytest.fail('Wrong target portrait context'))
    monkeypatch.setattr(PROJECT, 'bank', lambda state:
        bank if state is row['state'] else pytest.fail('Body bank must come from target document state'))
    def snapshot(state, path, candidate, *, context, document_id):
        calls.append((state, path, candidate, context, document_id))
        value = {'state': candidate, 'asset_sha256': ASSET, 'document_id': document_id,
            'support_assets': context['people_support_assets'], 'analyses': {ref['face_instance_id']: analysis}}
        if bad is not None: value[bad] = 'not-this-owner'
        return value
    def resolve(actual_graph, assets, actual_ref, actual_bank, actual_analysis, *, family):
        assert family == 'skin_finish' and actual_graph == graph and actual_ref == ref
        assert assets is context['people_support_assets'] and actual_bank is bank and actual_analysis is analysis
        return {}, SUPPORT
    monkeypatch.setattr(BODY, 'resolve', resolve)
    engine = SimpleNamespace(_people_export_snapshot=snapshot,
        _body_bank=lambda: pytest.fail('Batch must not borrow live engine body bank'))
    return engine, row, graph, payload, calls


def test_batch_finish_disclosure_uses_exact_document_snapshot_and_state_bank(monkeypatch):
    engine, row, graph, payload, calls = target_snapshot(monkeypatch)
    before = deepcopy(payload); result = R.for_target(engine, row, graph, payload, family='skin_finish')
    assert result['support_transfer'] == 'none'
    assert result['targets'][0]['scope'] == 'face-and-reviewed-body'
    assert result['targets'][0]['body_review_sha256'] == SUPPORT
    assert payload == before and len(calls) == 1
    assert calls[0][0] is row['state'] and calls[0][1] == row['path'] and calls[0][-1] == 'target-document'
    assert 'recipe' not in json.dumps(result) and 'body_ref' not in json.dumps(result)


@pytest.mark.parametrize('bad', ['state', 'asset_sha256', 'document_id'])
def test_finish_snapshot_owner_mismatch_refuses(monkeypatch, bad):
    engine, row, graph, payload, _ = target_snapshot(monkeypatch, bad=bad)
    with pytest.raises(ValueError, match='differs from the reviewed target'):
        R.for_target(engine, row, graph, payload, family='skin_finish')


def test_unknown_family_is_not_a_colour_or_finish_alias():
    graph, ref, analysis, payload, recipe = fixture()
    for family in (None, '', 'finish', 'skin_colour_body_visibility', 'lnx.skin_finish.v1'):
        with pytest.raises(ValueError): R.attached(graph, ref, family=family)
        with pytest.raises(ValueError): R.describe(graph, {}, ref, None, analysis, recipe, family=family)
        with pytest.raises(ValueError): R.for_target(None, None, graph, payload, family=family)


def test_default_colour_disclosure_preserves_existing_shape_and_signed_values():
    graph, ref, _, payload, recipe = colour_fixture(temperature=-.4, tint=.2)
    result = R.for_target(SimpleNamespace(), {'state': {}}, graph, payload)
    assert result == {'version': 1, 'support_transfer': 'none', 'targets': [
        {'face_ref': ref, 'scope': 'face-only', 'body_review_sha256': None}]}
    assert R.describe(graph, {}, ref, None, None, recipe) == result['targets'][0]
    assert R.for_target(None, None, graph, payload, family='skin_finish') is None


def test_finish_capture_excludes_review_from_portable_recipe_and_allows_stale_reset(monkeypatch):
    graph, ref, analysis, _, recipe = fixture(finish=True)
    from lumaretouch_engine import skin_finish_native as N
    monkeypatch.setattr(N, 'available', lambda: True)
    bank = {'live-body': 'owned'}; assets = {'live-support': 'owned'}
    engine = SimpleNamespace(_people_managed=lambda: True,
        _people_owner=lambda: SimpleNamespace(snapshot=lambda: deepcopy(graph)),
        _people_source=lambda: {'sha256': ASSET, 'width': 640, 'height': 480},
        _people_cursors={ASSET: ref['face_instance_id']},
        _people_targets={ASSET: {'scope': 'face', 'target_id': ref['face_instance_id'], 'face_ref': ref}},
        _people_analyses={ASSET: {ref['face_instance_id']: analysis}}, _people_support=assets,
        _body_bank=lambda: bank, _capture_state=lambda: {})
    def resolve(actual_graph, actual_assets, actual_ref, actual_bank, actual_analysis, *, family):
        assert family == 'skin_finish' and actual_assets is assets and actual_bank is bank
        return {}, SUPPORT
    monkeypatch.setattr(BODY, 'resolve', resolve)
    captured = C.capture(engine)
    assert captured[C.COVERAGE]['scope'] == 'face-and-reviewed-body'
    assert C.params_of(captured) == {'recipe': recipe} and C.FIELDS == (C.FIELD,)
    assert SUPPORT not in json.dumps(C.params_of(captured))
    def stale(*args, **kwargs): raise ValueError('Finish review is stale')
    monkeypatch.setattr(BODY, 'resolve', stale)
    captured = C.capture(engine)
    assert captured['_skin_finish_supported'] is False and captured[C.COVERAGE] is None
    with pytest.raises(ValueError): C.params_of(captured)
    C.install(captured, {'recipe': S.neutral()})
    assert captured[C.FIELD] == S.neutral()


def test_finish_hook_follows_actual_renderer_without_becoming_commit_authority():
    root = Path(__file__).resolve().parents[2] / 'engine/src/lumaretouch_engine'
    text = (root / 'people_batch_transfer.py').read_text()
    start = text.index('            validate(engine,row,staged)')
    finish = text.index("finish_coverage=skin_coverage(engine,row,staged,payload,family='skin_finish')", start)
    verify = text.index('SOURCE.verify_row(row,target_proof)', finish)
    assert start < finish < verify
    assert 'skin_finish_coverage' not in text[text.index('def commit('):]
    replay = (root / 'people_scope.py').read_text()
    assert "if SKIN_FINISH.S.active(finish_recipe):kwargs['strict_local']=True" in replay
    assert 'owner.commit(before,expected_fence=owner.fence)' in replay
