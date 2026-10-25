# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. No numerical, runtime or photographic acceptance implied."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import hair_volume_geometry as G
from lumaretouch_engine import hair_volume_recovery as RECOVERY
from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine import hair_volume_state as S
from lumaretouch_engine.hair_volume_support import digest


class ConstantField:
    def __init__(self, delta):
        self.delta = np.asarray(delta, dtype=np.float64)

    def evaluate(self, points):
        return np.broadcast_to(self.delta, points.shape).copy()


def test_nested_versions_are_not_inheritable_parameters():
    assert set(A.defaults()[S.OP]) == {'/crown/amount', '/sides/linked', '/sides/left', '/sides/right'}


def test_foreign_actual_field_conflict_refuses_instead_of_priority_dropping_hair():
    points = np.array([[11.25, 9.75], [20.125, 18.5]])
    base = ConstantField([0, 0]); hair = ConstantField([0, 2])
    for other in (ConstantField([1, 0]), ConstantField([0, -1])):
        field = G.ReviewedHairFace(base, hair, None, (other,))
        with pytest.raises(ValueError, match='another active face owner'):
            field.evaluate(points)
    isolated = G.ReviewedHairFace(base, hair, None, (ConstantField([0, 0]),))
    assert np.array_equal(isolated.evaluate(points), hair.evaluate(points))


def test_existing_inverse_chain_coordinate_is_used_without_second_rgb_warp():
    class ObservedHair:
        def evaluate(self, points):
            assert np.array_equal(points, np.array([[8.25, 7.5]]))
            return np.array([[0., 2.]])
    field = G.ReviewedHairFace(ConstantField([3, 2]), ObservedHair(), None, ())
    assert np.array_equal(field.evaluate(np.array([[11.25, 9.5]])), np.array([[3., 4.]]))


def recovery_case(*, changed=False, success=True, unknown=False):
    request = {'cmd': 'hair_volume', 'action': 'clear', 'request_id': 'clear-1',
               'people_context': {'source': 'synthetic'}, 'payload': {}}
    outcome = {'request_id': 'clear-1', 'action': 'clear', 'people_context': request['people_context'],
               'request_payload': {}, 'success': success, 'outcome_unknown': unknown}
    runtime = SimpleNamespace(revision=9, tainted=False, reason=None)
    engine = SimpleNamespace(_people_owner=lambda: SimpleNamespace(fence=6 if changed else 5),
        _project_recovery_runtime=runtime,
        _hair_volume_receipts={'clear-1': {'digest': digest(request), 'result': outcome}})
    boundary = {'message': request, 'started': True, 'returned': True, 'hair_volume_before_fence': 5}
    return engine, boundary, runtime


def test_noop_and_rejected_read_do_not_advance_committed_recovery_revision():
    for success in (False, True):
        engine, boundary, runtime = recovery_case(success=success)
        assert RECOVERY.finish(engine, boundary, None)
        assert runtime.revision == 9 and not runtime.tainted
    engine, boundary, runtime = recovery_case(changed=True)
    RECOVERY.finish(engine, boundary, None)
    assert runtime.revision == 10 and not runtime.tainted


def test_unknown_write_is_not_saved_as_committed_and_preserves_other_taint():
    engine, boundary, runtime = recovery_case(changed=True, unknown=True)
    RECOVERY.finish(engine, boundary, None)
    assert runtime.revision == 9 and runtime.tainted
    runtime.reason = 'another incomplete operation'
    RECOVERY.finish(engine, boundary, None)
    assert runtime.reason == 'another incomplete operation'


def test_already_neutral_recipe_does_not_write_four_default_overrides():
    from test_hair_volume_contract_unrun import fixture
    from lumaretouch_engine import hair_volume_project as P
    from lumaretouch_engine import hair_volume_support as SUPPORT
    state, _, _, _, record = fixture()
    state = SUPPORT.detach(state, record['face_ref'])
    assert P.set_recipe(state, 'owner', S.neutral()) == state
    assert SUPPORT.detach(state, record['face_ref']) == state


def test_derived_scalar_leaf_admission_defers_link_equality_to_complete_recipe():
    from lumaretouch_engine.creative_derived_effects import _leaf
    for path in ('/crown/amount', '/sides/left', '/sides/right'):
        _leaf(S.OP, path, .4)
    _leaf(S.OP, '/sides/linked', False)
    for path in ('/crown/version', '/sides/version', '/source'):
        with pytest.raises(ValueError):
            _leaf(S.OP, path, 1)


def test_publication_frame_waits_for_the_exact_terminal_receipt():
    from unittest import mock
    from lumaretouch_engine import hair_volume_controller as C
    from test_hair_volume_host_unrun import request
    engine = SimpleNamespace(_people_owner=lambda: SimpleNamespace(fence=3))
    emitted = []
    frame = {'event': 'frame', 'mode': 'people', 'doc_state': {'synthetic': True}}
    with mock.patch.object(C, 'clear', return_value=({'kind': 'cleared'}, frame)):
        C.execute(engine, request('clear'), emitted.append)
    assert emitted == []
    row = engine._hair_volume_receipts['request-1']
    assert row['success'] is True and row['frame_emitted'] is True
