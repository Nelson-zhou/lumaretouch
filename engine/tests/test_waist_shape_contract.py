# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED UNRUN. Synthetic contract data is not photographic evidence."""
from copy import deepcopy
import pytest
from lumaretouch_engine import waist_shape_state as S
from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine.waist_shape_field import WaistField


def synthetic_record():
    # Intentionally all unobserved. Never label these as actual model outputs.
    points=[{'index':i,'x':.5,'y':.5,'z':0.,'visibility':0.,'presence':0.} for i in range(33)]
    return E.create(source_frame={'sha256':'a'*64,'width':1200,'height':1600,'orientation':E.ORIENTATION},
                    values=points,backend_version='synthetic-negative-only',backend_code_sha256='b'*64,
                    model_id='synthetic-negative-fixture',model_sha256='c'*64,input_rgb_sha256='d'*64,
                    input_dimensions=(600,800))


def synthetic_bank():
    record=synthetic_record()
    run={'source':record['source'],'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False}
    state=B.add_run(B.empty(),run,initial_operations=(S.OPERATION_ID,),operation_policies=S.policies())
    return state,record['body_ref']


def support_data():
    return {'version':1,'upper':.4,'lower':.8,'stations':list(S.STATIONS),
            'negative':[.1]*9,'positive':[.12]*9,
            'region':{'selection_box':[.05,.05,.95,.95],'exclusions':[]},
            'confirmations':{flag:True for flag in S.FLAGS}}


def test_exact_requirement_and_orientation_only_anchors():
    assert S.REQUIREMENT_ID=='LNX-REF-PC-32473-C-8268ea3e37'
    assert S.OPERATION_ID=='lnx.waist_shape.v1'
    assert S.SUPPORT_KIND=='waist-source-visible-contour-v1'
    assert S.policy().required_anchors==(11,12,23,24)
    assert S.policies()==S.policies()


def test_original_inward_recipe_range_and_immutability():
    original={'version':1,'amount':.4};checked=S.check(original)
    checked['amount']=.2
    assert original['amount']==.4
    assert not S.active(S.neutral())
    assert S.active({'version':1,'amount':1})
    for amount in (-.001,1.001,True,None,float('nan'),float('inf')):
        with pytest.raises(ValueError):S.check({'version':1,'amount':amount})
    for key in ('linked','left','right','length','body_ref','support','strategy'):
        invalid=S.neutral();invalid[key]=None
        with pytest.raises(ValueError):S.check(invalid)


def test_manual_confirmation_cannot_upgrade_unobserved_anatomy():
    record=synthetic_record()
    with pytest.raises(ValueError):S.check_support(support_data(),record)
    state,ref=synthetic_bank()
    with pytest.raises(ValueError):
        B.set_support(state,ref,S.OPERATION_ID,S.SUPPORT_KIND,support_data(),operation_policies=S.policies())


def test_all_manual_confirmations_required_before_pose_admission():
    for flag in S.FLAGS:
        value=support_data();value['confirmations'][flag]=False
        with pytest.raises(ValueError):S.check_support(value,synthetic_record())
    value=support_data();value['confirmations']['ai_detected']=True
    with pytest.raises(ValueError):S.check_support(value,synthetic_record())


def test_no_missing_side_or_foreign_support_schema():
    for key in ('negative','positive','upper','lower'):
        value=support_data();del value[key]
        with pytest.raises(ValueError):S.check_support(value,synthetic_record())
    value=support_data();value['selection']={'predicted':True}
    with pytest.raises(ValueError):S.check_support(value,synthetic_record())


def test_neutral_field_never_loads_native(monkeypatch):
    import numpy as np
    from lumaretouch_engine import waist_shape_native as N
    monkeypatch.setattr(N,'native',lambda:(_ for _ in ()).throw(AssertionError('Neutral loaded native')))
    state,ref=synthetic_bank();field=WaistField(B.target(state,ref),None,(800,600))
    points=np.array([[12.125,45.75],[200.3,300.6]])
    assert np.array_equal(field.evaluate(points),np.zeros_like(points))
    assert field.resident_bytes()==field.render_scale.nbytes and field.supports==() and field.max_displacement==0
    assert field.facts['ai_segmentation'] is False
    assert field.facts['hidden_anatomy_inferred'] is False
    assert field.facts['runtime_quality_accepted'] is False


def test_active_without_source_review_refuses_before_native(monkeypatch):
    from lumaretouch_engine import waist_shape_native as N
    monkeypatch.setattr(N,'native',lambda:(_ for _ in ()).throw(AssertionError('Unreviewed loaded native')))
    state,ref=synthetic_bank()
    state=B.set_recipe(state,ref,{'version':1,'amount':.4},operation_id=S.OPERATION_ID,operation_policies=S.policies())
    with pytest.raises(ValueError):WaistField(B.target(state,ref),None,(800,600))


def test_neutral_waist_keeps_prior_order_identity():
    from lumaretouch_engine.body_pose_geometry import effective_order
    state,ref=synthetic_bank()
    assert effective_order(state).record()['version']==1
    before=deepcopy(effective_order(state).record())
    # Adding neutral waist alone must not promote a legacy neutral order to v4.
    assert before==effective_order(state).record()
    state=B.set_recipe(state,ref,{'version':1,'amount':.2},operation_id=S.OPERATION_ID,operation_policies=S.policies())
    assert effective_order(state).record()['version']==4
    assert effective_order(state).record()['operation_ids'][-1]==S.OPERATION_ID
