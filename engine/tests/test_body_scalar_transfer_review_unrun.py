# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: shared extraction and exact fixed-family routing contracts.

Nothing was imported, collected or executed while authoring. Existing torso
fixtures remain unchanged. These checks express future runtime acceptance only;
synthetic render doubles are not photographic or native numerical evidence.
"""
from dataclasses import FrozenInstanceError
import inspect

import pytest

from lumaretouch_engine import body_scalar_transfer_review as SHARED
from lumaretouch_engine import torso_length_scope as TORSO, waist_length_scope as WAIST
from lumaretouch_engine import torso_length_transfer_review as TR, waist_length_transfer_review as WR
from test_torso_length_transfer_review_unrun import render_fixture as torso_fixture
from test_waist_length_transfer_review_unrun import render_fixture as waist_fixture


@pytest.mark.parametrize('collection', [list, tuple, set, frozenset, dict.fromkeys])
def test_selector_routes_explicit_collections_and_exact_legacy_keys(collection):
    family = SHARED.select(collection([TORSO.OP]))
    assert family.scope is TORSO and family.review is TR
    assert (family.name, family.operation_id, family.wire_key, family.ack_key,
            family.private_key, family.frozen_key, family.prepared_key,
            family.port_name, family.preset_key) == (
        'torso_length', 'lnx.torso_length.v1', 'torso_transfer', 'torso_review_ack',
        'torso_review', 'torso_json', '_torso_prepared', 'torso', 'torso')
    with pytest.raises(FrozenInstanceError): family.ack_key = 'waist_review_ack'


def test_waist_has_distinct_fixed_wire_ledger_and_scope_identity():
    family = SHARED.select({WAIST.OP: {'version': 1, 'amount': .5}})
    assert family.scope is WAIST and family.review is WR
    assert (family.name, family.operation_id, family.wire_key, family.ack_key,
            family.private_key, family.frozen_key, family.prepared_key,
            family.port_name, family.preset_key) == (
        'waist_length', 'lnx.waist_length.v1', 'waist_transfer', 'waist_review_ack',
        'waist_review', 'waist_json', '_waist_prepared', 'waist', 'waist_review')
    assert WAIST.S.CONTROL_ID == 'LNX-REF-PC-32473-C-5d33f285bb'
    assert SHARED.select([]) is None and SHARED.select(['lnx.exposure.v1']) is None


@pytest.mark.parametrize('operations', [
    [TORSO.OP, WAIST.OP], [WAIST.OP, TORSO.OP],
    [TORSO.OP, 'lnx.exposure.v1'], [WAIST.OP, 'lnx.exposure.v1'],
    [WAIST.OP, WAIST.OP], [TORSO.OP, TORSO.OP],
    WAIST.OP, None, [True], [None], [['lnx.waist_length.v1']],
])
def test_ambiguous_mixed_duplicate_or_non_collection_routes_refuse(operations):
    with pytest.raises(ValueError): SHARED.select(operations)


def test_torso_signatures_and_shared_scope_implementation_stay_exact():
    signatures = {
        'check_params': ('raw',), 'target': ('state',), 'params_of': ('state',),
        'install': ('state', 'params'), 'validate_target': ('state', 'path', 'shape'),
        'bank_sha256': ('state',), 'undo_key': ('state',), 'restore': ('state', 'previous'),
    }
    assert TORSO.FIELDS == WAIST.FIELDS == ('_body_pose_bank',)
    for name, parameters in signatures.items():
        left, right = getattr(TORSO, name), getattr(WAIST, name)
        assert tuple(inspect.signature(left).parameters) == parameters
        assert inspect.signature(left) == inspect.signature(right)
        assert left.__func__ is right.__func__


def test_review_public_private_signatures_and_proof_shape_are_unchanged():
    signatures = {
        'checked': ('record',), 'rollback_record': ('record', 'before', 'revision'),
        'acknowledgments': ('raw', 'records'),
        'history_identity': ('engine', 'row', 'state', 'document', 'revision'),
        'prepare': ('engine', 'row', 'before', 'candidate', 'document', 'revision'),
        'verify': ('engine', 'row', 'before', 'candidate', 'document', 'revision', 'record'),
        '_target_identity': ('state', 'graph', 'proof', 'size'),
        '_view': ('engine', 'row', 'state', 'document', 'revision', 'expected'),
    }
    assert TR.FIELDS == WR.FIELDS == {
        'version', 'document_id', 'revision', 'source_proof', 'before_sha256',
        'candidate_sha256', 'before_people_sha256', 'candidate_people_sha256',
        'source_size', 'before_output_size', 'after_output_size', 'parameters',
        'before', 'after', 'body_ref', 'associated_face', 'body_support_sha256',
        'body_review_sha256', 'before_bank_sha256', 'candidate_bank_sha256'}
    assert TR.IDENTITY_FIELDS == WR.IDENTITY_FIELDS == {
        'document_id', 'revision', 'source_proof', 'candidate_sha256', 'people_sha256'}
    assert (TR.MAX_TARGETS, TR.PREVIEW_EDGE, TR.MAX_PNG_BYTES, TR.MAX_BASE64) == (8, 256, 150000, 200000)
    for name, parameters in signatures.items():
        left, right = getattr(TR, name), getattr(WR, name)
        assert tuple(inspect.signature(left).parameters) == parameters
        assert inspect.signature(left) == inspect.signature(right)
        assert left.__func__ is right.__func__


@pytest.mark.parametrize('review,fixture', [(TR, torso_fixture), (WR, waist_fixture)])
def test_existing_module_private_callback_patch_points_remain_live(tmp_path, monkeypatch, review, fixture):
    data = fixture(tmp_path, monkeypatch); original = review._target_identity; called = []
    def spy(*args):
        called.append(args[0])
        return original(*args)
    monkeypatch.setattr(review, '_target_identity', spy)
    review.prepare(*data[:4], 'target', '7')
    assert len(called) == 4 and len(data[4]) == 2


@pytest.mark.parametrize('review,fixture', [(TR, torso_fixture), (WR, waist_fixture)])
def test_public_budget_patch_point_is_consumed_by_shared_renderer(tmp_path, monkeypatch, review, fixture):
    data = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(review, 'MAX_PNG_BYTES', 1)
    with pytest.raises(ValueError, match='transport budget'):
        review.prepare(*data[:4], 'target', '7')
    assert len(data[4]) == 1


def test_same_proof_shape_never_allows_wrong_family_to_skip_target_support(tmp_path, monkeypatch):
    data = waist_fixture(tmp_path, monkeypatch)
    record, _ = WR.prepare(*data[:4], 'target', '7')
    # Shape is shared intentionally for compatibility, not an operation grant.
    # Replay must still route the frozen family and validate that family's body
    # intent, immutable support and review against the current target.
    assert TR.checked(record) == record
    with pytest.raises(ValueError): TR.verify(*data[:4], 'target', '7', record)
    assert len(data[4]) == 2
