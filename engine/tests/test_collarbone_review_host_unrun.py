# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN canonical review transaction/receipt fixtures.

The full-render seam is a synthetic before/after double inherited from the
body-skin fixture. These check routing and fences, not actual image results.
"""
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import skin_colour_body_host as H
from lumaretouch_engine import skin_colour_body_support as S
from lumaretouch_engine import people_state as P, collarbone_state as C
from test_body_skin_evenness_consent_unrun import host_fixture as base_fixture
from test_collarbone_support_unrun import clavicle, FAMILY


def fixture(monkeypatch):
    data = list(base_fixture(monkeypatch))
    data[3]['review']['clavicle'] = clavicle()
    data[0]._clavicle_reference_pixels = np.full((64, 64, 3), .3, np.float32)
    monkeypatch.setattr(H, '_reference_source', lambda engine, source, **kwargs:
        (engine._clavicle_reference_pixels, 'immutable-source', 256*1024**2))
    return data


def amount(graph, target):
    from lumaretouch_engine.people_algorithms import defaults, recipes
    from lumaretouch_engine.people_resolver import resolve
    return recipes(resolve(graph, target['target_id'], defaults()))[C.OP]['amount']


def test_new_family_has_its_own_capture_reference_and_candidate_slots(monkeypatch):
    engine, graph, target, _, _, _, _, _ = fixture(monkeypatch)
    families = ('skin_colour', 'skin_finish', 'body_skin_evenness', 'collarbone')
    assert len({H._capture(engine, graph, target, family=f)[0] for f in families}) == 4
    assert H._family('collarbone', C.OP)[3:] == ('_collarbone_reference', '_collarbone_preview')


def test_review_stages_exact_anatomy_and_positive_amount_without_mutating_live_graph(monkeypatch):
    engine, graph, target, payload, _, _, _, calls = fixture(monkeypatch)
    before_graph = deepcopy(graph); before_assets = deepcopy(engine._people_support)
    H.reference(engine, graph, target, {}, **FAMILY)
    shown = H.preview(engine, graph, target, payload, **FAMILY)
    assert graph == before_graph and engine._people_support == before_assets
    assert shown['review'] == payload['review'] and shown['amount'] == payload['amount']
    assert shown['family'] == 'collarbone' and shown['operation_id'] == C.OP
    assert len(calls) == 2 and amount(calls[0]['people_graph'], target) == 0
    candidate = calls[1]['people_graph']
    assert amount(candidate, target) == payload['amount']
    assert all(row['scope'] == 'face' and row['target_id'] == target['target_id']
               for row in candidate['overrides'] if row['operation_id'] == C.OP)
    assert [row for row in candidate['overrides'] if row['operation_id'] != C.OP] == graph['overrides']
    marks = []
    committed, reply = H.confirm(engine, graph, target,
        {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY,
        mark_started=lambda: marks.append(deepcopy(engine._people_support)))
    assert committed == candidate and marks == [before_assets]
    assert reply == {'kind': 'confirmed', 'attached': True, **FAMILY}
    assert len(engine._people_support) == len(before_assets)+1
    assert all(engine._people_support[key] == value for key, value in before_assets.items())
    assert engine._collarbone_reference is None and engine._collarbone_preview is None


@pytest.mark.parametrize('change', ['point', 'width', 'category', 'amount', 'labels', 'document', 'body', 'source-pixels'])
def test_changed_anatomy_or_canonical_identity_cannot_confirm_old_comparison(monkeypatch, change):
    engine, graph, target, payload, bank, _, version, _ = fixture(monkeypatch)
    H.reference(engine, graph, target, {}, **FAMILY)
    shown = H.preview(engine, graph, target, payload, **FAMILY)
    before = deepcopy(engine._people_support); pending = engine._collarbone_preview
    if change == 'point': pending['review']['clavicle']['curves'][0]['points'][1][1] += .01
    elif change == 'width': pending['review']['clavicle']['curves'][0]['width'] += .01
    elif change == 'category': pending['review']['clavicle']['category'] = 'elder_female'
    elif change == 'amount': pending['amount'] = .8
    elif change == 'labels': graph['faces'][target['target_id']]['labels'] = {'age_band': '儿童'}
    elif change == 'document': version.revision += 1
    elif change == 'source-pixels': engine._clavicle_reference_pixels[40, 30] = .4
    else: bank['revision'] += 1
    marks = []
    with pytest.raises(ValueError): H.confirm(engine, graph, target,
        {'preview_id': shown['preview_id'], 'reviewed': True}, **FAMILY,
        mark_started=lambda: marks.append(True))
    assert not marks and engine._people_support == before


def test_other_family_reference_and_preview_cannot_authorize_collarbone(monkeypatch):
    engine, graph, target, payload, _, _, _, calls = fixture(monkeypatch)
    H.reference(engine, graph, target, {}, family='skin_colour')
    before = deepcopy(engine._people_support)
    with pytest.raises(ValueError, match='reference'): H.preview(engine, graph, target, payload, **FAMILY)
    copied = deepcopy(engine._skin_body_reference)
    copied['fence'] = H._capture(engine, graph, target, **FAMILY)[0]
    engine._collarbone_reference = copied
    with pytest.raises(ValueError, match='reference'): H.preview(engine, graph, target, payload, **FAMILY)
    assert not calls and engine._people_support == before


def test_active_detach_refuses_and_neutral_detach_preserves_historical_bytes(monkeypatch):
    engine, graph, target, payload, bank, analysis, _, _ = fixture(monkeypatch)
    graph, assets = S.retain(graph, engine._people_support, target['face_ref'], bank,
                             analysis, payload['review'], **FAMILY)
    engine._people_support = assets
    active = P.set_override(graph, 'face', target['target_id'], C.OP, '/amount', .4)
    with pytest.raises(ValueError, match='zero'): H.detach(engine, active, target, {}, **FAMILY)
    assert engine._people_support == assets
    def no_body(): raise AssertionError('Neutral detach must not resolve stale body evidence')
    engine._body_bank = no_body
    detached, reply = H.detach(engine, graph, target, {}, **FAMILY)
    assert 'collarbone_visibility' not in detached['faces'][target['target_id']]['local_assets']
    assert engine._people_support == assets and reply['attached'] is False
    assert all(kind in detached['faces'][target['target_id']]['local_assets']
               for kind in ('skin_colour_body_visibility', 'skin_finish_body_visibility'))


def test_report_marks_conflicting_new_labels_stale_without_dropping_support(monkeypatch):
    engine, graph, target, payload, bank, analysis, _, _ = fixture(monkeypatch)
    graph, assets = S.retain(graph, engine._people_support, target['face_ref'], bank,
                             analysis, payload['review'], **FAMILY)
    engine._people_support = assets
    graph['faces'][target['target_id']]['labels'] = {'gender_label': '男'}
    report = H.report(engine, graph, engine._people_source(), target['target_id'], **FAMILY)
    assert report['attached'] is True and report['needs_review'] is True and report['reason']
