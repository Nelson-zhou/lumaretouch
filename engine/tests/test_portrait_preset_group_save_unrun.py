"""Authored boundary fixtures only. NOT EXECUTED; no acceptance claim."""
import pytest
from lumaretouch_engine.portrait_preset_group_save import _bank_delta, _outside
from lumaretouch_engine.people_state import empty


def test_unrelated_cursor_change_is_refused():
    with pytest.raises(ValueError):
        _bank_delta({'other': 'old'}, {'other': 'new'}, {'target'})


def test_target_cursor_change_is_bounded_to_target():
    _bank_delta({'target': 'old', 'other': 'same'},
                {'target': 'new', 'other': 'same'}, {'target'})


def test_landmark_evidence_cannot_be_overwritten_even_for_target():
    with pytest.raises(ValueError):
        _bank_delta({'proof': {'face_ref': {'asset_sha256': 'target'}}},
                    {'proof': {'face_ref': {'asset_sha256': 'target'}, 'changed': True}},
                    {'target'}, landmarks=True)


def test_new_foreign_landmark_is_refused():
    with pytest.raises(ValueError):
        _bank_delta({}, {'proof': {'face_ref': {'asset_sha256': 'other'}}},
                    {'target'}, landmarks=True)


def test_outside_projection_does_not_mutate_original():
    graph = empty()
    _outside(graph, set())
    assert 'revision' in graph
