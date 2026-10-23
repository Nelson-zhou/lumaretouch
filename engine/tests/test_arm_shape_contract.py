# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED UNRUN. Synthetic schema/negative fixtures, never portrait evidence."""
from copy import deepcopy
import pytest
from lumaretouch_engine import arm_shape_state as S, arm_shape_project as P
from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine.arm_shape_field import ArmField


def synthetic_record():
    # No synthetic point is ever allowed to authorize active image geometry.
    points=[{'index':i,'x':.5,'y':.5,'z':0.,'visibility':0.,'presence':0.} for i in range(33)]
    return E.create(source_frame={'sha256':'a'*64,'width':1200,'height':1600,'orientation':'exif_normalized_once'},values=points,
                    backend_version='synthetic-negative-only',backend_code_sha256='b'*64,
                    model_id='synthetic-negative-fixture',model_sha256='c'*64,input_rgb_sha256='d'*64,input_dimensions=(600,800))


def bank():
    record=synthetic_record();run={'source':record['source'],'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False}
    state=B.add_run(B.empty(),run,initial_operations=('lnx.shoulder_shape.v1',*S.OPERATION_IDS.values()),operation_policies=S.policies())
    return state,record['body_ref']


def manual_data(segment='left_upper'):
    return {'version':1,'segment':segment,'strategy':'reviewed-contour','stations':list(S.STATIONS),
            'negative':[.02]*9,'positive':[.02]*9,'region':{'selection_box':[.1,.1,.4,.6],'exclusions':[[.6,.1,.9,.8]]},
            'selection':None,'confirmations':{flag:True for flag in S.FLAGS}}


def test_exact_original_requirement_and_static_segment_anchors():
    assert S.REQUIREMENT_ID=='LNX-REF-PC-32473-C-5d25f1744f'
    assert [p.required_anchors for p in S.policies().values()]==[(11,13),(13,15),(12,14),(14,16)]
    assert S.policies()==S.policies()  # Stable callable identity for later registry admission.


def test_neutral_strategy_is_not_an_extra_warp():
    assert not S.active(S.neutral())
    assert S.check({'version':1,'strategy':'sam2-prompted-contour','amount':0})['amount']==0
    for n in (True,-.01,1.01,float('inf'),float('nan')):
        with pytest.raises(ValueError):S.check({'version':1,'strategy':'reviewed-contour','amount':n})
    for foreign in ('body_ref','support','mask','review','linked','overall'):
        value=S.neutral();value[foreign]={}
        with pytest.raises(ValueError):S.check(value)


def test_manual_review_cannot_promote_hidden_pose():
    record=synthetic_record()
    with pytest.raises(ValueError):S.check_support(manual_data(),record,segment='left_upper')
    state,ref=bank()
    with pytest.raises(ValueError):B.set_support(state,ref,S.OPERATION_IDS['left_upper'],S.SUPPORT_KIND,manual_data(),operation_policies=S.policies())


def test_neutral_field_has_no_native_load_or_inference(monkeypatch):
    import numpy as np
    from lumaretouch_engine import arm_shape_native as N
    monkeypatch.setattr(N,'native',lambda:(_ for _ in ()).throw(AssertionError('Neutral loaded Rust')))
    state,ref=bank();field=ArmField(B.target(state,ref),None,(800,600),S.OPERATION_IDS['left_upper'])
    points=np.array([[12.3,40.2],[80.,120.]])
    assert np.array_equal(field.evaluate(points),np.zeros_like(points))
    assert field.resident_bytes()==0 and field.max_displacement==0 and field.supports==()


def test_active_missing_review_refuses_before_native():
    state,ref=bank();op=S.OPERATION_IDS['left_forearm']
    state=B.set_recipe(state,ref,{'version':1,'strategy':'reviewed-contour','amount':.4},operation_id=op,operation_policies=S.policies())
    with pytest.raises(ValueError,match='own exact'):ArmField(B.target(state,ref),None,(800,600),op)


def test_one_bank_roundtrip_preserves_independent_segment_intent():
    state,ref=bank();op=S.OPERATION_IDS['left_upper']
    changed=B.set_recipe(state,ref,{'version':1,'strategy':'reviewed-contour','amount':.3},operation_id=op,operation_policies=S.policies())
    assert P.unpack(P.pack(changed))==changed and len(changed['bodies'])==1
    for other in S.OPERATION_IDS.values():
        if other!=op:assert B.operation(changed,ref,other)==B.operation(state,ref,other)
    source=B.target(changed,ref)['record']['source'];snap=P.snapshot(changed,source)
    assert P.check_snapshot(snap,source)==changed
    bad=deepcopy(snap);bad['body_operation_order']['operation_ids'].reverse()
    with pytest.raises(ValueError):P.check_snapshot(bad,source)


def test_linking_requires_both_explicit_targets():
    from lumaretouch_engine.arm_shape_host import _targets
    with pytest.raises(ValueError):_targets({'targets':['left_upper'],'linked':True})
    assert _targets({'targets':['left_upper','right_upper'],'linked':True})==['left_upper','right_upper']
    assert _targets({'targets':['left_forearm'],'linked':False})==['left_forearm']


def test_masks_are_actual_lossless_retained_pixels_not_points():
    import numpy as np
    from lumaretouch_engine.arm_shape_selection import encode_mask,decode_mask
    mask=np.zeros((13,17),np.uint8);mask[3:10,7:9]=1
    value=encode_mask(mask);assert np.array_equal(decode_mask(value),mask)
    changed=deepcopy(value);changed['sha256']='0'*64
    with pytest.raises(ValueError):decode_mask(changed)
    with pytest.raises(ValueError):encode_mask(np.ones((4,4),np.uint8)*2)


def test_actual_mask_contamination_is_rejected_not_erased():
    import numpy as np
    from lumaretouch_engine.arm_shape_selection import _mask_ownership,reject_ownership
    mask=np.zeros((100,100),np.uint8);mask[40:60,40:60]=1
    with pytest.raises(ValueError):_mask_ownership(mask,{'selection_box':[.1,.1,.9,.9],'exclusions':[[.4,.4,.6,.6]]})
    evidence={'other_bodies':[],'faces':[],'torso_polygon':[[.3,.3],[.7,.3],[.7,.7],[.3,.7]]}
    with pytest.raises(ValueError):reject_ownership(mask,evidence)
    assert int(mask.sum())==400


def test_model_input_replay_differs_by_pixels():
    import numpy as np
    from lumaretouch_engine import prompted_mask_source as SAM
    from lumaretouch_engine.arm_shape_selection import verify_input
    pixels=np.zeros((16,16,3),np.uint16);_,digest=SAM.inference_image(pixels)
    selection={'binding':{'input_sha256':digest}};verify_input(pixels,selection)
    pixels[4,4]=65535
    with pytest.raises(ValueError):verify_input(pixels,selection)


def test_history_protects_other_family_and_people_graph(monkeypatch):
    state,ref=bank();op=S.OPERATION_IDS['left_upper'];changed=B.set_recipe(state,ref,{**S.neutral(),'amount':.4},operation_id=op,operation_policies=S.policies())
    patch=P.history_patch(state,changed,people_sha256='e'*64)
    monkeypatch.setattr(P,'people_digest',lambda _: 'f'*64)
    with pytest.raises(ValueError):P.replay_patch(changed,patch,undo=True,people_state={},expected_bank_sha256=P.graph_digest(changed))
    monkeypatch.setattr(P,'people_digest',lambda _: 'e'*64)
    restored=P.replay_patch(changed,patch,undo=True,people_state={},expected_bank_sha256=P.graph_digest(changed))
    assert B.operation(restored,ref,op)['recipe']==S.neutral()
    assert B.operation(restored,ref,'lnx.shoulder_shape.v1')==B.operation(state,ref,'lnx.shoulder_shape.v1')


def test_ordinary_contours_cannot_claim_sam_receipt():
    from lumaretouch_engine.arm_shape_selection import support_from_proposal
    with pytest.raises(ValueError):support_from_proposal({'proposals':[{'refusal':'actual segmentation failed'}]},0,{})
    value=S.neutral();value['strategy']='AI-manual-alias'
    with pytest.raises(ValueError):S.check(value)


def test_cancel_before_start_retains_a_tombstone():
    from lumaretouch_engine.arm_shape_job import ArmProposalJobs
    jobs=ArmProposalJobs();jobs.release('cancel-before-start')
    # Intentionally invalid inputs: the tombstone must return before admission,
    # imports, available-memory reads or worker creation can be attempted.
    result=jobs.start('cancel-before-start',None,None,None,None,None,None,None)
    assert result['phase']=='done' and result['success'] is False and not jobs.jobs


def test_closed_document_owner_never_admits_delayed_start():
    from lumaretouch_engine.arm_shape_job import ArmProposalJobs
    jobs=ArmProposalJobs();jobs.close()
    result=jobs.start('late-start',None,None,None,None,None,None,None)
    assert result['phase']=='done' and result['success'] is False and not jobs.jobs
