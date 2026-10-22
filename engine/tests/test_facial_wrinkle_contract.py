"""Unexecuted here. Qoder/local gate: contracts, not real-portrait quality proof."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import facial_wrinkle_state as S
from lumaretouch_engine import facial_wrinkle_recovery as R
from lumaretouch_engine.facial_wrinkle_runtime import landmarks_identity, skin_support


def test_eight_regions_nine_independent_strengths_and_persisted_link():
    assert len(S.KEYS) == 9 and len(S.CONTROL_IDS) == 9
    assert not S.active({S.LINK_KEY: 1})
    assert not S.active_enhance({S.LINK_KEY: 1})
    for key in S.KEYS:
        value = S.check({key: .4})
        assert S.active(value)
        assert sum(value[k] > 0 for k in S.KEYS) == 1
        assert S.preset(value) == value


@pytest.mark.parametrize('value', [True, False, None, '0.5', float('nan'), float('inf'), -1, 1.01])
def test_invalid_amount_is_rejected(value):
    with pytest.raises(ValueError): S.check({S.KEYS[0]: value})


@pytest.mark.parametrize('value', [.1, .5, .999999, True, '1'])
def test_unlock_is_not_continuous(value):
    with pytest.raises(ValueError): S.check({S.LINK_KEY: value})


def test_linking_preserves_unequal_sides():
    values = S.check({'wrinkle_nasolabial_left': .2, 'wrinkle_nasolabial_right': .8, S.LINK_KEY: 1})
    linked = S.patch(values, {S.LINK_KEY: 0})
    assert linked['wrinkle_nasolabial_left'] == .2
    assert linked['wrinkle_nasolabial_right'] == .8


def test_face_recovery_is_source_and_landmark_owned_not_index_owned():
    lm = np.zeros((478, 3), np.float32)
    lm[:, :2] = .5
    pc = SimpleNamespace(backend='mediapipe', landmarks=lm, face_index=0)
    source = {'sha256': 'a' * 64, 'width': 1000, 'height': 1000}
    original = R.owner(source, pc)
    value = {'targets': [{'target': R.TARGET, 'enabled': True, 'owner': original}]}
    R.verify(value, source, pc)
    pc.face_index = 1  # index does not provide identity
    R.verify(value, source, pc)
    changed = lm.copy(); changed[33, 0] += .001
    pc.landmarks = changed
    with pytest.raises(ValueError, match='人物已改变'): R.verify(value, source, pc)
    assert landmarks_identity(lm) != landmarks_identity(changed)
    with pytest.raises(ValueError): R.check_row(value['targets'][0], {**source, 'sha256': 'b' * 64})


def test_old_anonymous_facial_recovery_is_not_migrated_by_guessing():
    with pytest.raises(ValueError): R.check_owner(None)
    R.check_row({'target': 'skin_smoothing'}, None)
    with pytest.raises(ValueError): R.check_row({'target': R.TARGET}, None)


def test_semantic_support_never_falls_back_to_person_or_template():
    pc = SimpleNamespace(backend='template', semantic_model_sha256='a'*64, masks={'skin': np.ones((5, 5), np.float32)})
    assert skin_support(pc) is None
    pc.backend = 'mediapipe'; pc.masks = {'portrait_parts': np.ones((5, 5), np.float32)}
    assert skin_support(pc) is None
    pc.masks['skin'] = np.zeros((5, 5), np.float32)
    assert np.count_nonzero(skin_support(pc)) == 0


def test_shared_enhance_transport_preserves_region_intent_and_strict_link():
    from lumaretouch_engine.ops import enhance as E
    value = E.check_amounts({'sclera': .2, 'wrinkle_forehead': .7, S.LINK_KEY: 1})
    assert value['sclera'] == .2 and value['wrinkle_forehead'] == .7
    assert value[S.LINK_KEY] == 1
    for invalid in (.5, True, '1'):
        with pytest.raises(E.EnhanceError): E.check_amounts({S.LINK_KEY: invalid})
    assert not S.active_enhance(E.check_amounts({S.LINK_KEY: 1}))


def test_stale_face_recovery_suspends_only_its_operator():
    from lumaretouch_engine.effect_recovery_stage import EffectRecoveryStage
    stage = EffectRecoveryStage('cpu', (2, 2))
    stage.required = {'facial_wrinkles'}
    stage.suspended_targets = {'facial_wrinkles': '人物身份已改变'}
    before = np.zeros((1, 3, 2, 2), np.float32)
    after = np.ones_like(before)
    assert stage.apply('facial_wrinkles', before, after) is before
    assert stage.apply('skin_smoothing', before, after) is after
    assert stage.suspended is None
