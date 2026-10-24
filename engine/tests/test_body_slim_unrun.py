# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Synthetic schemas are NOT detector or photo acceptance.

No imports, native calls, collection, tests, compiler or inference ran while
these fixtures were authored. Installed-native cases never install/build.
"""
from copy import deepcopy
from unittest.mock import patch
import numpy as np
import pytest
from lumaretouch_engine import body_slim_state as S, body_slim_native as N
from lumaretouch_engine import body_slim_runtime as R, body_slim_project as P
from lumaretouch_engine import body_pose_state as B, body_pose_evidence as E
from lumaretouch_engine import body_pose_manifest as M, people_state as PEOPLE
from lumaretouch_engine.body_slim_field import BodySlimField

SOURCE = {'sha256':'a'*64,'width':1001,'height':1601,'orientation':E.ORIENTATION}
BUDGET = 16*1024*1024


def synthetic_record():
    points = [dict(index=i,x=.5,y=.28,z=0.,visibility=.99,presence=.99) for i in range(33)]
    xy = {11:(.46,.38),12:(.54,.38),13:(.44,.43),14:(.56,.43),
          15:(.43,.48),16:(.57,.48),17:(.425,.49),18:(.575,.49),
          19:(.43,.50),20:(.57,.50),21:(.435,.49),22:(.565,.49),
          23:(.47,.52),24:(.53,.52),25:(.47,.63),26:(.53,.63),
          27:(.47,.70),28:(.53,.70),29:(.465,.71),30:(.535,.71),31:(.46,.72),32:(.54,.72)}
    for i,(x,y) in xy.items(): points[i].update(x=x,y=y)
    return E.create(source_frame=SOURCE,values=points,backend_version='synthetic-unrun-body-slim',
        backend_code_sha256='b'*64,model_id=M.MODEL_ID,model_sha256=M.MODEL_SHA256,
        input_rgb_sha256='c'*64,input_dimensions=(1001,1601))


def geometry():
    # Geometric octagon ONLY for arithmetic/schema fixtures, not human anatomy.
    return {'version':1,'method':S.METHOD,'outline':[[.46,.24],[.54,.24],[.60,.30],
        [.60,.70],[.54,.76],[.46,.76],[.40,.70],[.40,.30]],
        'collar_box':[.10,.05,.90,.95],'confirmations':{k:True for k in S.FLAGS}}


def fixture(amount=.5, review=True):
    record=synthetic_record();ref=record['body_ref']
    state=B.add_run(B.empty(),{'source':SOURCE,'records':[record],'detector_limit':4,
        'limit_reached':False,'census_complete':False},initial_operations=(S.OPERATION_ID,),operation_policies=S.policies())
    evidence={'backend':'synthetic-unrun-body-slim','detector_model_sha256':'d'*64,
        'semantic_model_sha256':None,'landmark_digest':'e'*64,'status':'verified',
        'source_width':1001,'source_height':1601,'orientation':E.ORIENTATION}
    face=PEOPLE.new_face(SOURCE['sha256'],[.46,.26,.54,.33],evidence)
    people=PEOPLE.empty();people['faces'][face['face_instance_id']]=face
    people['persons']['synthetic-person']={'anonymous':True}
    people['revision']=people['association_revision']=1
    people['links']=[{'face_instance_id':face['face_instance_id'],'person_id':'synthetic-person',
        'state':'confirmed','confirmation_revision':1}]
    state=B.associate(state,ref,'synthetic-person',people,user_confirmed=True)
    data=R.bind_support_review(geometry(),B.target(state,ref),people)
    if review:
        state=B.set_support(state,ref,S.OPERATION_ID,S.SUPPORT_KIND,data,operation_policies=S.policies())
        state=B.review(state,ref,points_sha256=record['points_sha256'],visible_anchors=list(S.REQUIRED_ANCHORS),
            ownership_confirmed=True,operation_id=S.OPERATION_ID,
            support_sha256=B.operation(state,ref,S.OPERATION_ID)['support_sha256'],operation_policies=S.policies())
    state=B.set_recipe(state,ref,{'version':1,'amount':amount},operation_id=S.OPERATION_ID,operation_policies=S.policies())
    return state,people,ref,data


def test_exact_requirement_and_independent_whole_width_recipe():
    assert S.CONTROL_ID=='LNX-REF-PC-32473-C-bc54b9eb3c'
    assert S.OPERATION_ID=='lnx.body_slim.v1'
    assert S.REQUIRED_ANCHORS==tuple(range(33))
    for amount in (-1.,0.,1.):
        assert S.portable({'version':1,'amount':amount})=={'version':1,'amount':amount}
    for amount in (True,None,float('nan'),float('inf'),10**1000,1.001,-1.001):
        with pytest.raises(ValueError):S.check({'version':1,'amount':amount})
    for extra in ('waist','leg','body_ref','support'):
        with pytest.raises(ValueError):S.check({**S.neutral(),extra:None})


def test_real_polygon_required_not_bbox_or_pose_hull():
    _,_,_,data=fixture()
    assert len(S.support_vector(data))==20
    for outline in ([],data['outline'][:4],data['outline']+[data['outline'][0]],
                    [data['outline'][i] for i in (0,2,1,3,4,5,6,7)]):
        with pytest.raises(ValueError):S.check_support({**data,'outline':outline})
    with pytest.raises(ValueError):S.check_support({**data,'outline':None,'box':[.4,.24,.6,.76]})
    assert not S.inside(data['outline'],data['outline'][0])


@pytest.mark.parametrize('flag',S.FLAGS)
def test_each_manual_ownership_background_confirmation_required(flag):
    _,_,_,data=fixture();data['confirmations'][flag]=False
    with pytest.raises(ValueError):S.check_support(data)


@pytest.mark.parametrize('index',S.REQUIRED_ANCHORS)
def test_actual_hidden_point_never_promoted_by_review(index):
    bank,_,ref,data=fixture();record=deepcopy(B.target(bank,ref)['record'])
    record['points'][index]['visibility']=.79;record['points_sha256']=E.content_digest(record['points'])
    with pytest.raises(ValueError):S.check_support(data,record)


def test_wrong_face_and_source_digests_require_re_review():
    bank,people,ref,data=fixture();row=B.target(bank,ref)
    bad=deepcopy(data);bad['associated_face_evidence_sha256']='f'*64
    with pytest.raises(ValueError):R.validate_face_review(bad,row,people)
    bad=deepcopy(data);bad['associated_face_ref']['asset_sha256']='f'*64
    with pytest.raises(ValueError):S.check_support(bad,row['record'])


def test_neutral_does_not_load_native_or_require_silhouette():
    bank,_,ref,_=fixture(amount=0,review=False)
    with patch.object(N,'prepare',side_effect=AssertionError('must not load native')):
        field=BodySlimField(B.target(bank,ref),None,(800,496))
        np.testing.assert_array_equal(field.evaluate([[20.3,60.1]]),[[0.,0.]])
        assert field.max_displacement==0 and field.supports==()


def test_another_disabled_body_refused_before_native():
    bank,people,ref,_=fixture();other=synthetic_record()
    # E.create generates independent BodyRef; both observations are synthetic.
    bank=B.add_run(bank,{'source':SOURCE,'records':[other],'detector_limit':4,
        'limit_reached':False,'census_complete':False},initial_operations=(),operation_policies=S.policies())
    bank['bodies'][other['body_ref']['body_instance_id']]['enabled']=False
    with patch.object(N,'prepare',side_effect=AssertionError('multi-person must fail before native')):
        with pytest.raises(R.BodySlimRefused):R.prepare_fields(bank,SOURCE['sha256'],(800,496),people_state=people,byte_budget=BUDGET,source_frame=SOURCE)


def test_detector_limit_refused_and_not_relabelled_as_complete_census():
    bank,people,_,_=fixture();bank['analysis_runs'][SOURCE['sha256']]['limit_reached']=True
    with patch.object(N,'prepare',side_effect=AssertionError('truncated census must fail before native')):
        with pytest.raises(R.BodySlimRefused):R.prepare_fields(bank,SOURCE['sha256'],(800,496),people_state=people,byte_budget=BUDGET,source_frame=SOURCE)


def test_project_roundtrip_keeps_immutable_source_owned_silhouette():
    bank,_,_,_=fixture();assert P.unpack(P.pack(bank))==bank
    assert P.effective_order(bank).version==10
    assert P.effective_order(bank).operation_ids[-1]==S.OPERATION_ID
    frozen=P.snapshot(bank,SOURCE);assert P.check_snapshot(frozen,SOURCE)==bank


@pytest.mark.parametrize('amount',[-1.,0.,1.])
def test_installed_native_actual_width_and_height_contract(amount):
    if not N.available():pytest.skip('Separate permitted packaging required; never build during fixture collection')
    bank,_,ref,data=fixture(amount);record=B.target(bank,ref)['record']
    points=[[p[k] for k in ('x','y','z','visibility','presence')] for p in record['points']]
    state=N.prepare(points,[amount],S.support_vector(data),(1601,1001));facts=N.facts(state)
    assert facts['whole_person_width_factor']==pytest.approx(1-.08*amount)
    assert facts['measured_person_width']==pytest.approx(200.)
    assert not state.flags.writeable
    with pytest.raises(ValueError):state.setflags(write=True)
    # Query known FORWARD transformed silhouette endpoints; inverse recovers them.
    scale=1-.08*amount
    for y in (384.,800.,1216.):
        target=np.array([[500.-100.*scale,y],[500.+100.*scale,y]])
        delta=N.evaluate(state,target)
        np.testing.assert_allclose(target-delta,[[400.,y],[600.,y]],atol=1e-7,rtol=0)
        np.testing.assert_array_equal(delta[:,1],[0.,0.])
    outside=np.array([[0.,0.],[1000.,1600.],[100.,800.],[900.,800.]])
    np.testing.assert_array_equal(N.evaluate(state,outside),np.zeros_like(outside))
    with pytest.raises(ValueError):N.evaluate(state,[[-.001,600.]])


def test_unavailable_native_is_explicit_no_python_warp_fallback():
    with patch.object(N,'native',side_effect=OSError('missing installed artifact')):
        assert N.available() is False
        with pytest.raises(OSError):N.prepare([[.5,.5,0,1,1]]*33,[.5],[.1,.1,.9,.9]+[n for p in geometry()['outline'] for n in p],(1601,1001))
