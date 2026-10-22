"""Authored fixtures only; Qoder runs these after integration, not acceptance evidence."""
import numpy as np
import pytest
from lumaretouch_engine import reference_color_state as S,reference_color_scope as Scope
from lumaretouch_engine.reference_color_stage import ReferenceColorStage
from lumaretouch_engine.reference_color_review import candidate_key


def recipe():
    return {**S.empty(),'strength':1.,'log2_gains':[.2,-.1,.1],
        'source':{'sha256':'a'*64,'width':100,'height':100},
        'reference':{'source':{'sha256':'b'*64,'width':100,'height':100},
                     'render_sha256':'c'*64,'asset_id':'d'*64}}


def test_neutral_exact_same_object_rgb8_rgb16_float():
    for dtype in (np.uint8,np.uint16,np.float32,np.float64):
        a=np.zeros((4,4,3),dtype=dtype)
        assert ReferenceColorStage(None).apply_np(a) is a


def test_active_u16_does_not_collapse_to_eight_bits():
    a=np.arange(32000,32300,dtype=np.uint16).reshape(10,10,3)
    b=ReferenceColorStage(recipe()).apply_np(a)
    assert b.dtype==np.uint16
    assert len(np.unique(b[...,0]))>90


def test_extended_float_not_clipped_and_geometry_unchanged():
    a=np.array([[[-.1,.5,1.5]]],np.float32)
    b=ReferenceColorStage(recipe()).apply_np(a)
    assert b.shape==a.shape and b[0,0,0]<0 and b[0,0,2]>1


def test_manual_state_preserved_and_portable_has_no_target_gains():
    before={'_exposure':(1.,20.,.1),'_curves':{'manual':True}}
    result=S.install(before,recipe())
    assert result['_exposure']==before['_exposure'] and result['_curves']==before['_curves']
    assert S.KEY not in before
    p=Scope.params_of(result)
    assert set(p)=={'version','strength','reference'}
    with pytest.raises(ValueError): Scope.apply_prepared(before,p,None)
    with pytest.raises(ValueError): Scope.check_params({**p,'log2_gains':[1,1,1]})


def test_candidate_identity_preserves_all_manual_edits():
    a={'_exposure':(1.,0.,0.)}
    assert candidate_key(a)==candidate_key({**a,S.KEY:recipe()})
    assert candidate_key(a)!=candidate_key({'_exposure':(2.,0.,0.)})


def test_identity_fit_still_retains_portable_reference_intent():
    value=recipe();value['log2_gains']=[0.,0.,0.]
    assert not S.active(value)
    assert Scope.params_of({S.KEY:value})['reference']==value['reference']


def test_scope_restore_preserves_other_manual_fields_and_exact_target_recipe():
    from lumaretouch_engine import scope as SC,optics_auto_scope as OA
    before={S.KEY:recipe(),'_reference_color_bundle':['fixture'], '_exposure':(0.,)*7}
    current={**before,S.KEY:S.empty(),'_exposure':(1.,)*7}
    restored=SC.restore_modules(current,before,[S.OP])
    assert restored[S.KEY]==before[S.KEY] and restored['_exposure']==current['_exposure']
    assert OA.before_params(before,[S.OP])!=OA.before_params(current,[S.OP])
    assert S.KEY not in OA.candidate({}, {S.OP:Scope.params_of(before)})


def test_project_cannot_drop_reference_bundle_silently():
    from lumaretouch_engine.reference_color_project import validate_records
    with pytest.raises(ValueError):validate_records({S.KEY:recipe()})


def test_candidate_identity_excludes_only_owned_asset_and_fit():
    a={'_exposure':(1.,0.,0.)}
    assert candidate_key(a)==candidate_key({**a,'_reference_color_bundle':[np.zeros(9,np.uint8)]})
    assert candidate_key(a)!=candidate_key({**a,'_crop_rotation':10.})
