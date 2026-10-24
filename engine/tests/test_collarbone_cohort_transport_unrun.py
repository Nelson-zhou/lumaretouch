"""AUTHORED / UNRUN: cohort frozen authority and compact receipt contracts."""
from types import SimpleNamespace
from pathlib import Path
import pytest
from lumaretouch_engine.batch_preflight import collarbone_required, collarbone_cohort


def plan(modules=(), mode='persistent_association', required=True):
    return SimpleNamespace(modules=modules, params=lambda: {'_people_transfer': {
        'mode': mode, 'collarbone_visual_required': required}})


def test_empty_scope_unlink_uses_frozen_cohort_requirement():
    assert collarbone_required(plan()) and collarbone_cohort(plan())


def test_other_selected_module_does_not_erase_active_cohort_requirement():
    assert collarbone_required(plan(['lnx.deform.v1']))


@pytest.mark.parametrize('value', [False, None, 1, 'true', {}])
def test_caller_like_truthy_flag_cannot_authorize_cohort_review(value):
    assert not collarbone_required(plan(['lnx.collarbone.v1'], required=value))


def test_noncohort_visual_requirement_still_requires_actual_operation():
    assert collarbone_required(plan(['lnx.collarbone.v1'], mode='ordinary', required=False))
    assert not collarbone_required(plan([], mode='ordinary'))
    assert not collarbone_cohort(plan(['lnx.collarbone.v1'], mode='ordinary'))


def test_claim_and_overflow_keep_cohort_marker_and_source_first_records():
    source=(Path(__file__).parents[1]/'src/lumaretouch_engine/batch_preflight.py').read_text()
    assert "**({'collarbone_cohort':True} if collarbone_cohort(plan) else {})" in source
    assert "if collarbone_cohort(plan):ack['collarbone_cohort']=True" in source
    assert "for target in plan.targets if not target.blocked" in source
