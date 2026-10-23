"""Authored, NOT RUN in the source-only tranche. No photo/quality evidence.

Synthetic algebra/state fixtures deliberately do not invoke a pose detector or
claim a verified body. Real image acceptance is a separate qoder checklist.
"""
from copy import deepcopy
import pytest
from lumaretouch_engine import shoulder_shape_state as S,body_pose_evidence as E
from lumaretouch_engine import body_pose_state as B,shoulder_shape_project as P
from lumaretouch_engine.shoulder_shape_host import HostPorts,ShoulderHostAdapter


def synthetic_record():
    # All confidence is zero. Review must reject these fabricated test points.
    points=[{'index':i,'x':.5,'y':.5,'z':0.,'visibility':0.,'presence':0.} for i in range(33)]
    return E.create(source_frame={'sha256':'a'*64,'width':1200,'height':1600,'orientation':'exif_normalized_once'},values=points,backend_version='test-fixture',backend_code_sha256='b'*64,model_id='synthetic-unit-test-only',model_sha256='c'*64,input_rgb_sha256='d'*64,input_dimensions=(600,800))


def bank():
    record=synthetic_record();run={'source':record['source'],'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False}
    return B.add_run(B.empty(),run),record['body_ref']


def test_neutral_and_bilateral_non_destructive_relink():
    assert not S.active(S.neutral())
    r=S.link(S.neutral(),'width',False);r=S.adjust(r,'width','left',.3);r=S.adjust(r,'width','right',-.2)
    r=S.link(r,'width',True)
    assert (r['width']['left'],r['width']['right'])==(.3,-.2)
    r=S.adjust(r,'width','right',.1)
    assert r['width']['left']==r['width']['right']==.1
    assert r['square']==S.neutral()['square']


def test_strict_ranges_and_no_identity_in_portable_recipe():
    for value in (float('nan'),True,1.01,-.01):
        with pytest.raises(ValueError):S.adjust(S.neutral(),'square','left',value)
    r=S.neutral();r['body_ref']={}
    with pytest.raises(ValueError):S.portable(r)


def test_body_ref_is_never_face_ref():
    state,ref=bank();wrong={'asset_sha256':ref['asset_sha256'],'face_instance_id':ref['body_instance_id'],'analysis_revision':0}
    with pytest.raises(ValueError):E.ref(wrong)
    other=deepcopy(ref);other['analysis_revision']=1
    with pytest.raises(ValueError):B.target(state,other)


def test_low_confidence_not_promoted_by_user_review():
    state,ref=bank();row=B.target(state,ref)
    with pytest.raises(ValueError):B.review(state,ref,points_sha256=row['record']['points_sha256'],visible_anchors=list(E.ANCHORS),ownership_confirmed=True)


def test_actual_point_digest_and_all33_are_required():
    record=synthetic_record();record['points'][11]['x']=.6
    with pytest.raises(ValueError):E.check(record)
    record=synthetic_record();record['points'].pop()
    with pytest.raises(ValueError):E.check(record)


def test_project_and_history_preserve_independent_body_intent():
    state,ref=bank();changed=B.set_recipe(state,ref,S.adjust(S.neutral(),'width','left',.2))
    assert P.unpack(P.pack(changed))==changed
    patch=P.history_patch(state,changed)
    restored=P.replay_patch(changed,patch,undo=True,expected_association_revision=changed['association_revision'])
    assert B.operation(restored,ref)['recipe']==S.neutral()
    later=B.set_recipe(changed,ref,S.adjust(S.neutral(),'width','left',.3))
    with pytest.raises(ValueError):P.replay_patch(later,patch,undo=True,expected_association_revision=later['association_revision'])


def test_request_reuse_does_not_execute_twice():
    state,ref=bank();binding={'document_id':'doc','document_epoch':'epoch','document_revision':0,'asset_sha256':'a'*64};published=[]
    def publish(before,after,prepared,patch,request):
        nonlocal state
        published.append(request['request_id']);state=after
        return {'state_revision':after['revision'],'publication':{'request_id':request['request_id'],'rendered':True,'unapplied_reason':None}}
    adapter=ShoulderHostAdapter(HostPorts(lambda:binding,lambda:state,lambda:{'association_revision':0},lambda candidate:object(),publish))
    request={'request_id':'r','gesture_id':'g',**{k:binding[k] for k in ('document_id','document_epoch','document_revision')},'state_revision':state['revision'],'association_revision':0,'people_association_revision':0,'body_ref':ref,'action':'body_status','payload':{'enabled':False}}
    first=adapter.execute(request);assert first==adapter.execute(request);assert published==['r']
    request['payload']['enabled']=True
    with pytest.raises(ValueError):adapter.execute(request)


def test_v1_body_bank_migration_is_only_shoulder_authority():
    state,ref=bank();old=deepcopy(state);old['version']=1;old.pop('support_assets')
    row=old['bodies'][ref['body_instance_id']];item=row.pop('operations')[S.OPERATION_ID]
    row['recipe']=item['recipe'];row['review']=None
    envelope={'version':1,'state':old,'content_sha256':E.content_digest(old)}
    migrated=P.unpack(envelope)
    assert migrated['version']==2 and set(B.target(migrated,ref)['operations'])=={S.OPERATION_ID}
    assert migrated['revision']==state['revision'] and B.operation(migrated,ref)['review'] is None


def test_unknown_operation_retained_but_not_rendered_or_silently_exported():
    from lumaretouch_engine import body_pose_operations as O
    from lumaretouch_engine.body_pose_geometry import require_prepared
    state,ref=bank();row=B.target(state,ref)
    row['operations']['fixture.future.v1']={'enabled':True,'recipe':{'version':1,'intent':.4},'review':None,'support_sha256':None}
    assert P.unpack(P.pack(state))==state
    with pytest.raises(ValueError):require_prepared(state,ref['asset_sha256'],())
    disabled=B.set_operation_enabled(state,ref,'fixture.future.v1',False)
    assert B.operation(disabled,ref,'fixture.future.v1')['recipe']=={'version':1,'intent':.4}
    assert O.active_operations(B.target(disabled,ref))==()


def test_new_neutral_operation_increments_revision():
    state,ref=bank();B.target(state,ref)['operations']={}
    changed=B.set_recipe(state,ref,S.neutral())
    assert changed['revision']==state['revision']+1


def test_operation_review_cannot_authorize_other_anchors():
    # Structural review isolation, not a real pose or quality acceptance case.
    from lumaretouch_engine import body_pose_operations as O
    state,ref=bank();record=B.target(state,ref)['record']
    fake={'enabled':True,'recipe':{'version':1,'amount':0},'support_sha256':None,
          'review':{'operation_id':'fixture.future.v1','body_ref':ref,'points_sha256':record['points_sha256'],'visible_anchors':[11,12],'ownership_confirmed':True,'review_revision':state['revision'],'support_sha256':None}}
    policy=O.OperationPolicy('fixture.future.v1',lambda:{'version':1,'amount':0},lambda v:v,lambda v:v['amount']!=0,(23,24,25,26,27,28))
    B.target(state,ref)['operations']['fixture.future.v1']=fake
    with pytest.raises(ValueError):B.check(state,operation_policies={policy.operation_id:policy})


def test_support_asset_history_preserves_operation_ownership():
    from lumaretouch_engine import body_pose_operations as O
    state,ref=bank();name='fixture.support.v1'
    policy=O.OperationPolicy(name,lambda:{'version':1,'amount':0},lambda v:v,lambda v:v['amount']!=0,(23,24),'fixture-contour',lambda data,record:data)
    changed=B.set_support(state,ref,name,'fixture-contour',{'version':1,'test_only':True},operation_policies={name:policy})
    asset=B.support(changed,ref,name)
    assert asset['body_ref']==ref and asset['operation_id']==name
    patch=P.history_patch(state,changed)
    undone=P.replay_patch(changed,patch,undo=True,expected_association_revision=changed['association_revision'])
    assert name not in B.target(undone,ref)['operations'] and undone['support_assets']==changed['support_assets']
    redone=P.replay_patch(undone,patch,undo=False,expected_association_revision=undone['association_revision'])
    assert B.support(redone,ref,name)==asset


def test_same_body_subfields_chain_at_displaced_not_original_coordinates():
    # Pure numerical fixtures: not anatomy and never supplied to inference/render.
    import numpy as np
    from lumaretouch_engine.body_pose_geometry import group_subfields,FrozenBodyOrder
    record=synthetic_record()
    class FixtureField:
        def __init__(self,op,axis):
            self.operation_id=op;self.axis=axis;self.body_ref=record['body_ref'];self.record=record;self.shape=(1600,1200);self.supports=((np.array([600.,800.]),50.),);self.max_displacement=100.;self.associated_face_id=None
        def evaluate(self,points):
            value=np.zeros_like(points);value[:,self.axis]=points[:,1-self.axis]*.01;return value
        def resident_bytes(self):return 16
    a,b=FixtureField('fixture.a',0),FixtureField('fixture.b',1)
    order=FrozenBodyOrder(99,('fixture.a','fixture.b'))
    groups=group_subfields((b,a),order);assert len(groups)==1
    points=np.array([[10.,20.]])
    expected=a.evaluate(points)+b.evaluate(points-a.evaluate(points))
    assert np.array_equal(groups[0].evaluate(points),expected)
    assert not np.array_equal(expected,a.evaluate(points)+b.evaluate(points))
    with pytest.raises(ValueError):group_subfields((a,a),order)


def test_prepared_field_binding_refuses_stale_recipe_same_body_ref():
    from types import SimpleNamespace
    from lumaretouch_engine import body_pose_operations as O
    from lumaretouch_engine.body_pose_geometry import require_prepared
    state,ref=bank();state=B.set_recipe(state,ref,S.adjust(S.neutral(),'width','left',.1));row=B.target(state,ref)
    field=SimpleNamespace(operation_id=S.OPERATION_ID,record=row['record'],body_ref=ref,input_binding_sha256=O.field_binding(row,S.OPERATION_ID))
    with pytest.raises(ValueError,match='review'):require_prepared(state,ref['asset_sha256'],(field,))
    newer=B.set_recipe(state,ref,S.adjust(S.neutral(),'width','left',.2))
    with pytest.raises(ValueError,match='stale'):require_prepared(newer,ref['asset_sha256'],(field,))


def test_multibody_export_snapshot_survives_canonical_json_order():
    import json
    state,ref=bank();record=synthetic_record()
    state=B.add_run(state,{'source':record['source'],'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False})
    state['bodies']=dict(sorted(state['bodies'].items(),reverse=True))
    value=P.snapshot(state,record['source']);encoded=json.loads(json.dumps(value,sort_keys=True))
    assert P.check_snapshot(encoded,record['source'])==P.unpack(value['bank'])


def test_canonical_decoder_alignment_not_arbitrary_aspect_tolerance():
    frame={'sha256':'a'*64,'width':4000,'height':6000,'orientation':E.ORIENTATION}
    E.whole_source_shape(frame,(6000,4000))
    E.whole_source_shape(frame,(3520,2344))
    with pytest.raises(ValueError):E.whole_source_shape(frame,(3520,2304))
    with pytest.raises(ValueError):E.whole_source_shape(frame,(3520,2345))
    with pytest.raises(ValueError):E.whole_source_shape(frame,(12000,8000))


def test_cleared_owned_history_is_not_resurrected_and_unavailable_is_preserved(monkeypatch):
    from types import SimpleNamespace
    from lumaretouch_engine import people_history_persistence as history
    asset='a'*64
    saved={asset:{'path':'missing.jpg','stacks':{'undo':[],'redo':[]}}}
    def missing(_row):raise FileNotFoundError('authored missing-source case')
    monkeypatch.setattr(history,'asset_for',missing)
    state,_ref=bank()
    unopened={'path':'missing.jpg','opened':True,'state':{'_body_pose_bank':P.pack(state)},'undo':[],'redo':[]}
    engine=SimpleNamespace(_project={'people_document_history':deepcopy(saved)},_docs=[unopened])
    project={'assets':{}};history.save(engine,project)
    assert project['people_document_history']==saved
    unopened['_history_owned']=True
    project={'assets':{}};history.save(engine,project)
    assert project['people_document_history']=={}


def test_decoded_body_source_stamp_is_required_and_rechecked(monkeypatch):
    from lumaretouch_engine import body_pose_render as render,local_mask_state as source
    state,_ref=bank();frame=next(iter(state['bodies'].values()))['record']['source']
    snap={'body_pose':P.snapshot(state,frame)};stamp=(1,2,3,4,5)
    monkeypatch.setattr(source,'file_stamp',lambda _path:stamp)
    monkeypatch.setattr(source,'source_digest',lambda _path:frame['sha256'])
    with pytest.raises(ValueError):render.check_export_decode(snap,'source.jpg',None,(1600,1200))
    render.check_export_decode(snap,'source.jpg',stamp,(1600,1200))
    assert snap['body_pose_source_stamp']==list(stamp)
    monkeypatch.setattr(source,'file_stamp',lambda _path:(1,2,3,4,6))
    with pytest.raises(ValueError):render.check_export_decode(snap,'source.jpg',stamp,(1600,1200))
