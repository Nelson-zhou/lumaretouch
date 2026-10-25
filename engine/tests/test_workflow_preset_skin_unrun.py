"""Authored UNRUN: skin recipe admission is not prepared-target/runtime proof."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from lumaretouch_engine import workflow_preset_review as R


PRESET = {'modules': {'lnx.skin.v1': {'strength': 0.35, 'enabled': True},
                      'lnx.exposure.v1': {'ev': 0.2}}}


def state():
    return {'_creative_base': None, '_channel': 'skin', '_strength': 0.1,
            '_precompute': SimpleNamespace(num_faces=1, masks={'skin': object()})}


def test_skin_color_recipe_supported_only_as_complete_selected_scope():
    assert R.support_reason(PRESET) is None
    assert R.support_reason({'modules': {'lnx.skin.v1': PRESET['modules']['lnx.skin.v1']}}) is None
    for op in ('lnx.blemish.v1', 'lnx.unknown.v1'):
        preset = deepcopy(PRESET)
        preset['modules'][op] = {'strength': 0.5}
        assert R.support_reason(preset) == 'unsupported_workflow_preset_module'


def test_existing_pin_is_only_recipe_identity_not_prepared_target_authority(monkeypatch):
    from lumaretouch_engine import workflow_preset_catalogue as catalogue
    monkeypatch.setattr(catalogue, 'resolve', lambda *_: PRESET)
    assert R._preset('saved-skin', 'a' * 64) == PRESET


def test_handoff_refuses_before_loading_or_remembering_any_target(monkeypatch):
    from lumaretouch_engine import workflow_preset_handoff as handoff
    monkeypatch.setattr(handoff, 'resolve', lambda *_: PRESET)
    # No mutation methods exist: an original return target must first be loaded.
    owner = handoff.PresetHandoff(SimpleNamespace(engine=SimpleNamespace(_image_loaded=False)))
    command = {'command': {'operation': {'preset_id': 'saved-skin', 'preset_sha256': 'a' * 64}}}
    with pytest.raises(ValueError, match='distinct loaded original'):
        owner.start(command, {})
    assert owner.active is None


def test_color_only_admission_remains_available():
    assert R.support_reason({'modules': {'lnx.exposure.v1': {'ev': 0.2}}}) is None


def test_target_check_delegates_to_retained_owner_not_legacy_batch_guess(monkeypatch):
    from lumaretouch_engine import workflow_preset_retained_skin as retained
    engine, row, before, calls = object(), {}, state(), []
    monkeypatch.setattr(retained, 'require_target', lambda *args: calls.append(args))
    R._require_portrait_target(engine, row, before, PRESET)
    assert calls == [(engine, row, before)]
    assert before['_channel'] == 'skin' and before['_strength'] == 0.1


def test_color_only_keeps_original_no_face_requirement():
    R._require_portrait_target(object(), {}, {}, {'modules': {'lnx.exposure.v1': {}}})


def test_candidate_transfers_strength_only_not_target_masks_or_identity():
    before = state()
    before['_repair_ops'] = []
    before['_retained_target_identity'] = {'id': 'target-not-preset'}
    after = R._candidate(before, {'modules': {'lnx.skin.v1': {'strength': 0.35, 'enabled': True}}})
    assert after['_strength'] == 0.35 and before['_strength'] == 0.1
    for key in ('_precompute', '_repair_ops', '_retained_target_identity'):
        assert after[key] is before[key]
    assert after['_channel'] == before['_channel'] == 'skin'
