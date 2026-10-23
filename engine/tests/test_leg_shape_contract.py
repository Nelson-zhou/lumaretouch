# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored UNRUN. Synthetic negative/schema fixtures are not photo evidence.

No fixture is a real detector observation, no model is downloaded, and no test
claims photographic acceptance. Native/photo tests are separate qoder cases.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import body_pose_evidence as E, body_pose_state as B
from lumaretouch_engine import leg_shape_state as S, leg_shape_project as P
from lumaretouch_engine.leg_shape_field import LegField


def synthetic_record():
    # Every confidence is zero; this deliberately cannot authorize leg geometry.
    points=[{'index':i,'x':.5,'y':.5,'z':0.,'visibility':0.,'presence':0.} for i in range(33)]
    return E.create(source_frame={'sha256':'a'*64,'width':1200,'height':1600,'orientation':'exif_normalized_once'},
                    values=points,backend_version='synthetic-test-only',backend_code_sha256='b'*64,
                    model_id='synthetic-negative-fixture',model_sha256='c'*64,input_rgb_sha256='d'*64,input_dimensions=(600,800))


def bank():
    record=synthetic_record();run={'source':record['source'],'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False}
    state=B.add_run(B.empty(),run,initial_operations=('lnx.shoulder_shape.v1',S.OPERATION_ID),operation_policies=S.policies())
    return state,record['body_ref']


def support_data():
    # Algebraic widths only, no human source review and no valid measured record.
    return {'version':1,'method':'user-reviewed-visible-silhouette','stations':[.25,.5,.75],
            'segments':{key:{'negative':[.02,.025,.02],'positive':[.02,.025,.02],'support_radius':.05} for key in S.SEGMENTS},
            **{key:True for key in ('joints_visible','separate_legs','not_foreshortened','ownership_confirmed','background_support_reviewed')}}


def test_overall_is_atomic_set_not_third_strength():
    r=S.adjust(S.neutral(),'thigh',.4);r=S.adjust(r,'calf',-.2)
    assert r=={'version':1,'thigh':.4,'calf':-.2}
    r=S.adjust(r,'overall',.25)
    assert S.vector(r)==[.25,.25] and set(r)=={'version','thigh','calf'}
    assert S.adjust(r,'overall',.25)==r
    r['overall']=.25
    with pytest.raises(ValueError):S.check(r)


def test_strict_portable_ranges_and_no_left_right_guess():
    for amount in (True,float('nan'),float('inf'),-1.01,1.01):
        with pytest.raises(ValueError):S.adjust(S.neutral(),'thigh',amount)
    r=S.neutral();r['linked']=True
    with pytest.raises(ValueError):S.portable(r)
    for foreign in ('body_ref','points','support','mask','review'):
        r=S.neutral();r[foreign]={}
        with pytest.raises(ValueError):S.portable(r)


def test_source_support_needs_every_explicit_review():
    value=support_data();assert S.check_support(value)==value
    for flag in ('joints_visible','separate_legs','not_foreshortened','ownership_confirmed','background_support_reviewed'):
        changed=deepcopy(value);changed[flag]=False
        with pytest.raises(ValueError):S.check_support(changed)
    changed=deepcopy(value);changed['segments']['left_thigh']['negative'][0]=None
    with pytest.raises(ValueError):S.check_support(changed)
    changed=deepcopy(value);changed['segments']['left_thigh']['support_radius']=.025
    with pytest.raises(ValueError):S.check_support(changed)


def test_low_confidence_cannot_be_promoted_by_contour_review():
    state,ref=bank()
    with pytest.raises(ValueError):B.set_support(state,ref,S.OPERATION_ID,S.SUPPORT_KIND,support_data(),operation_policies=S.policies())
    with pytest.raises(ValueError):B.review(state,ref,operation_id=S.OPERATION_ID,points_sha256=B.target(state,ref)['record']['points_sha256'],visible_anchors=list(S.REQUIRED_ANCHORS),ownership_confirmed=True,operation_policies=S.policies())
    with pytest.raises(ValueError):S.policy_check_support(support_data(),synthetic_record())


def test_neutral_field_does_not_load_native(monkeypatch):
    import numpy as np
    from lumaretouch_engine import leg_shape_native as N
    def forbidden(*args,**kwargs):raise AssertionError('Neutral field tried to load native')
    monkeypatch.setattr(N,'native',forbidden)
    state,ref=bank();field=LegField(B.target(state,ref),None,(800,600))
    p=np.array([[10.25,20.75],[100.,300.]])
    assert np.array_equal(field.evaluate(p),np.zeros_like(p))
    assert field.shape==(800,600) and field.resident_bytes()==0 and field.max_displacement==0


def test_no_silent_native_fallback_on_active_unreviewed_leg():
    state,ref=bank();state=B.set_recipe(state,ref,S.adjust(S.neutral(),'thigh',.3),operation_id=S.OPERATION_ID,operation_policies=S.policies())
    with pytest.raises(ValueError,match='Leg-specific'):LegField(B.target(state,ref),None,(800,600))


def test_body_bank_roundtrip_and_frozen_order_not_second_bank():
    state,ref=bank();state=B.set_recipe(state,ref,S.adjust(S.neutral(),'overall',.2),operation_id=S.OPERATION_ID,operation_policies=S.policies())
    assert P.unpack(P.pack(state))==state
    source=B.target(state,ref)['record']['source'];snap=P.snapshot(state,source)
    assert snap['body_operation_order']=={'version':2,'operation_ids':['lnx.shoulder_shape.v1',S.OPERATION_ID]}
    assert P.check_snapshot(snap,source)==state
    changed=deepcopy(snap);changed['body_operation_order']['operation_ids'].reverse()
    with pytest.raises(ValueError):P.check_snapshot(changed,source)
    assert len(state['bodies'])==1 and len(B.target(state,ref)['operations'])==2


def test_leg_history_does_not_authorize_person_graph_changes(monkeypatch):
    # Fake hash only to isolate history fencing, not an authorization fixture.
    state,ref=bank();changed=B.set_recipe(state,ref,S.adjust(S.neutral(),'thigh',.2),operation_id=S.OPERATION_ID,operation_policies=S.policies())
    patch=P.history_patch(state,changed,people_sha256='e'*64)
    monkeypatch.setattr(P,'people_digest',lambda _: 'f'*64)
    with pytest.raises(ValueError,match='Canonical people'):P.replay_patch(changed,patch,undo=True,people_state={},expected_bank_sha256=P.graph_digest(changed))
    monkeypatch.setattr(P,'people_digest',lambda _: 'e'*64)
    restored=P.replay_patch(changed,patch,undo=True,people_state={},expected_bank_sha256=P.graph_digest(changed))
    assert B.operation(restored,ref,S.OPERATION_ID)['recipe']==S.neutral()
    assert B.operation(restored,ref,'lnx.shoulder_shape.v1')==B.operation(state,ref,'lnx.shoulder_shape.v1')
    later=B.set_recipe(changed,ref,S.adjust(S.neutral(),'thigh',.3),operation_id=S.OPERATION_ID,operation_policies=S.policies())
    with pytest.raises(ValueError):P.replay_patch(later,patch,undo=True,people_state={},expected_bank_sha256=P.graph_digest(later))


def test_reanalysis_preserves_recipe_but_requires_new_review():
    state,ref=bank();state=B.set_recipe(state,ref,S.adjust(S.neutral(),'calf',-.3),operation_id=S.OPERATION_ID,operation_policies=S.policies())
    result=B.reanalyse(state,ref,synthetic_record(),user_confirmed=True)
    newref={**ref,'analysis_revision':state['revision']+1}
    item=B.operation(result,newref,S.OPERATION_ID)
    assert item['recipe']['calf']==-.3 and item['review'] is None and item['support_sha256'] is None
    with pytest.raises(ValueError):B.target(result,ref)


def test_neutral_leg_preserves_exact_shoulder_geometry_identity_and_v1_snapshot():
    from lumaretouch_engine import shoulder_shape_state as Shoulder, shoulder_shape_project as Legacy
    from lumaretouch_engine import body_pose_render as Render
    state,ref=bank();row=B.target(state,ref);row['operations'].pop(S.OPERATION_ID)
    state=B.set_recipe(state,ref,Shoulder.adjust(Shoulder.neutral(),'width','left',.2))
    source=B.target(state,ref)['record']['source']
    old_record=Render.geometry_record({'_body_pose_bank':Legacy.pack(state)})
    old_snapshot=Legacy.snapshot(state,source)
    assert P.check_snapshot(old_snapshot,source)==state
    neutral=B.set_recipe(state,ref,S.neutral(),operation_id=S.OPERATION_ID)
    assert Render.geometry_record({'_body_pose_bank':P.pack(neutral)})==old_record
    assert P.snapshot(neutral,source)['body_operation_order']==old_snapshot['body_operation_order']
    active=B.set_recipe(neutral,ref,S.adjust(S.neutral(),'calf',.2),operation_id=S.OPERATION_ID)
    assert P.effective_order(active).version==2
    disabled=B.set_operation_enabled(active,ref,S.OPERATION_ID,False)
    assert P.effective_order(disabled).version==1
    assert Render.geometry_record({'_body_pose_bank':P.pack(disabled)})==old_record
    forged=P.snapshot(active,source);forged['body_operation_order']=old_snapshot['body_operation_order']
    with pytest.raises(ValueError):P.check_snapshot(forged,source)


def test_installed_leg_does_not_authorize_future_operations():
    from lumaretouch_engine import body_pose_operations as O
    from lumaretouch_engine.body_pose_geometry import require_prepared
    state,ref=bank()
    assert S.OPERATION_ID in O.policies()
    assert 'lnx.arm_shape.v1' not in O.policies()
    B.target(state,ref)['operations']['fixture.future.v1']={'enabled':True,'recipe':{'version':1},'review':None,'support_sha256':None}
    retained=P.unpack(P.pack(state))
    with pytest.raises(ValueError):require_prepared(retained,ref['asset_sha256'],())


def test_leg_frame_accepts_decoder_alignment_not_arbitrary_crop(monkeypatch):
    from lumaretouch_engine import leg_shape_native as N
    def forbidden(*args,**kwargs):raise AssertionError('Neutral input loaded native')
    monkeypatch.setattr(N,'native',forbidden)
    state,ref=bank();row=B.target(state,ref)
    LegField(row,None,(528,400))  # one scale with downward ALIGN=8 rounding
    with pytest.raises(ValueError):LegField(row,None,(528,401))
    with pytest.raises(ValueError):LegField(row,None,(512,400))


def test_invalid_publication_cannot_be_reconciled_as_lost_notification():
    from lumaretouch_engine.leg_shape_host import LegHostAdapter,HostPorts
    from lumaretouch_engine.body_pose_host import BodyPoseHostMixin
    invalid={'phase':'pending','request_id':'bad-map','outcome_unknown':True,'publication_invalid':True,'success':False}
    adapter=LegHostAdapter(HostPorts(lambda:None,lambda:None,lambda:None,lambda _:None,lambda *args:None,lambda _:None,lambda *args:None))
    adapter.receipts['bad-map']={'digest':'a'*64,'result':invalid}
    terminal={'phase':'done','request_id':'bad-map','outcome_unknown':False,'success':True}
    with pytest.raises(ValueError):adapter.resolve_publication('bad-map',actual_result=terminal)
    class Host:
        _body_authoritative={'bad-map':terminal}
        def _body_adapter(self,operation):return adapter
    assert BodyPoseHostMixin._body_status(Host(),'bad-map','leg_shape')==invalid
