# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: source wiring and independent intent/transfer fixtures.

No collection, product import, rendering, compilation or test execution occurred
while authoring. These assertions do not constitute photographic acceptance.
"""
from copy import deepcopy
from pathlib import Path
import ast
import pytest

from lumaretouch_engine import collarbone_state as S
from lumaretouch_engine import collarbone_scope as C
from lumaretouch_engine import people_algorithms as A
from lumaretouch_engine import scope as SC
from lumaretouch_engine import creative_derived_effects as D
from lumaretouch_engine.skin_colour_transfer_review import describe, _state

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src' / 'lumaretouch_engine'


def test_distinct_operation_and_default_do_not_reinterpret_old_recipes():
    assert S.OP == 'lnx.collarbone.v1'
    assert S.neutral() == {'version': 1, 'amount': 0.0}
    assert A.defaults()[S.OP] == {'/amount': 0.0}
    assert S.OP in D.OPERATIONS and _state('collarbone') is S
    assert A.specifications()['lnx.body_skin_evenness.v1'][0] == {'version': 1, 'amount': 0.0}


@pytest.mark.parametrize('amount', [-.01, 1.01, True, float('nan'), float('inf'), '.5'])
def test_rejects_invalid_scalar_amount(amount):
    with pytest.raises((ValueError, TypeError)):
        S.check({'version': 1, 'amount': amount})


@pytest.mark.parametrize('extra', ['clavicle', 'category', 'body_ref', 'face_ref', 'recipe', 'source', 'mask'])
def test_portable_recipe_cannot_carry_anatomy_or_identity(extra):
    with pytest.raises(ValueError):
        C.check_params({'recipe': {'version': 1, 'amount': .3, extra: {}}})


def test_scalar_params_are_the_only_portable_fields():
    assert C.check_params({'recipe': {'version': 1, 'amount': .3}}) == {'recipe': {'version': 1, 'amount': .3}}
    with pytest.raises(ValueError): C.check_params({'recipe': {'version': 1, 'amount': .3}, 'review': {}})
    assert SC.MODULES[S.OP]['state_fields'] == C.FIELDS
    assert SC.MODULES[S.OP]['single_face'] is True


def test_generic_derived_install_is_still_fenced_before_any_write():
    state = {'_creative_base': {'sentinel': True}, C.FIELD: S.neutral()}
    before = deepcopy(state)
    with pytest.raises(ValueError): C.install(state, {'recipe': {'version': 1, 'amount': .2}})
    assert state == before


def test_missing_target_does_not_turn_amount_zero_into_owner_authority():
    with pytest.raises(ValueError): C.require_target({}, S.neutral())


def test_layer_source_stage_and_support_ownership_ports_exist():
    for name, needles in {
        'people_host.py': ["result['collarbone']", '_collarbone_reference'],
        'people_host_commands.py': ['collarbone_reference', 'collarbone_confirm', "family='collarbone'"],
        'creative_derived_effects.py': ['collarbone_preview', 'collarbone_visibility'],
        'people_project.py': ['collarbone'],
        'people_export.py': ['collarbone'],
        'people_render_runtime.py': ['collarbone_assets', 'collarbone_layer'],
        'people_owned_inputs.py': ['collarbone_assets'],
        'people_pipeline.py': ['collarbone'],
        'vram.py': ["source_effect(self,'collarbone',out)"],
    }.items():
        text = (SOURCE/name).read_text()
        ast.parse(text)
        assert all(needle in text for needle in needles), name


def test_transfer_rechecks_target_local_support_after_full_aggregate_preparation():
    text = (SOURCE/'people_batch_transfer.py').read_text()
    assert "payload['collarbone_coverage']" in text
    assert "(COLLARBONE,'collarbone')" in text
    assert "payload.get(family+'_coverage')" in text
    assert text.index('prepare_scoped(engine,plans,targets)') < text.rindex("payload.get(family+'_coverage')")


def test_trace_and_applicability_metadata_are_not_registered_portable_leaves():
    assert set(A.defaults()[S.OP]) == {'/amount'}
    assert SC.check_params(S.OP, {'recipe': S.neutral()}) == {'recipe': S.neutral()}


def test_readonly_scope_capture_uses_own_native_and_current_source_admission():
    text = (SOURCE/'collarbone_scope.py').read_text()
    assert 'from .collarbone_native import available' in text
    assert 'I.proof(engine, row, graph' in text
    assert "family=FAMILY" in text
    assert "support_transfer" not in C.check_params({'recipe': S.neutral()})


def test_unknown_implicit_legacy_preset_save_does_not_add_new_clavicle_intent():
    text = (SOURCE/'preset_controller.py').read_text()
    assert 'SC.COLLARBONE.OP)] if requested is None else requested' in text
