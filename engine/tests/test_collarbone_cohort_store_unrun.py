# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: persistent source+target immutable image ownership."""
import pytest
from lumaretouch_engine import collarbone_visual_store as C
from lumaretouch_engine import people_cross_owner as ASSOCIATION
from test_collarbone_visual_store_unrun import fixture


@pytest.fixture(autouse=True)
def unrelated_eye_family_admission(monkeypatch):
    # This legacy cache fixture supplies synthetic collarbone-only plans rather
    # than complete association owner graphs; explicitly mock unrelated admission.
    from lumaretouch_engine import eye_bag_cohort_review
    monkeypatch.setattr(eye_bag_cohort_review, 'records', lambda plan: None)


def cohort(count=2):
    values = fixture(count)
    plan = values[1]; plan.source_id = 'document-0'; plan.modules = []
    members = [{'document_id': 'document-'+str(index), 'scope_id': 'document-'+str(index),
                'original_sha256': 'a'*64, 'ref': {'asset_sha256': 'a'*64,
                'face_instance_id': 'fixture-face-'+str(index), 'analysis_revision': 0}}
               for index in range(count)]
    capsule = ASSOCIATION.descriptor('fixture-collarbone', plan.source_id, members,
                                     [{'op': 'lnx.collarbone.v1', 'path': '/amount', 'value': .4}])
    review = {key: value for key, value in capsule.items() if key != 'local_document_id'}
    review['operation'] = 'unlink'
    plan.params = lambda: {'_people_transfer': {'mode': 'persistent_association',
                                             'collarbone_visual_required': True,
                                             'portrait_cohort_required': False, 'review': review}}
    return values


def test_unlink_empty_selected_modules_still_reads_both_cohort_members():
    owner, plan, displays, records, request, _ = cohort()
    C.attach(owner.store, plan, displays); C.verify_available(owner.store, plan)
    assert list(C._records(plan)) == ['document-0', 'document-1']
    for document in records:
        result = C.retrieve(owner, {**request, 'document_id': document})
        assert result['document_id'] == document


def test_other_selected_operation_does_not_hide_retained_collarbone_visuals():
    owner, plan, displays, _, request, _ = cohort()
    plan.modules = ['lnx.deform.v1']
    C.attach(owner.store, plan, displays)
    assert C.retrieve(owner, request)['success'] is True


def test_cohort_cannot_omit_source_member_or_reorder_it():
    for mode in ('omit', 'reorder'):
        owner, plan, displays, _, _, _ = cohort()
        plan.targets = plan.targets[1:] if mode == 'omit' else list(reversed(plan.targets))
        with pytest.raises(ValueError, match='source first'): C.attach(owner.store, plan, displays)


def test_atomic_cohort_cannot_skip_blocked_member():
    owner, plan, displays, _, _, _ = cohort(); plan.targets[1].blocked = 'unavailable'
    with pytest.raises(ValueError, match='every atomic member'): C.attach(owner.store, plan, displays)


@pytest.mark.parametrize('flag', [False, None, 1, 'true'])
def test_only_actual_true_frozen_marker_can_authorize_cohort_images(flag):
    owner, plan, displays, _, _, _ = cohort(); plan.modules = ['lnx.collarbone.v1']
    plan.params = lambda: {'_people_transfer': {'mode': 'persistent_association',
                                             'collarbone_visual_required': flag}}
    with pytest.raises(ValueError, match='actual frozen'): C.attach(owner.store, plan, displays)


def test_request_cannot_invent_a_cohort_marker_or_change_scope():
    owner, plan, displays, _, request, _ = cohort(); C.attach(owner.store, plan, displays)
    with pytest.raises(ValueError): C.retrieve(owner, {**request, 'collarbone_cohort': True})


def test_unlink_consumption_cleans_all_members_not_just_targets():
    owner, plan, displays, _, request, _ = cohort(); C.attach(owner.store, plan, displays)
    owner.store.pending.clear(); C.prune(owner.store)
    assert owner.store._collarbone_visual_images.count == 0
    for document in ('document-0', 'document-1'):
        with pytest.raises(ValueError): C.retrieve(owner, {**request, 'document_id': document})
