"""AUTHORED / UNRUN: immutable derived body export ownership contracts.

Synthetic zero-confidence pose observations exercise source fencing only. They
are not detection, anatomical, deformation, native-render or visual acceptance.
No product imports or tests were executed while authoring this fixture.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import body_pose_render as R,body_pose_evidence as E
from lumaretouch_engine import body_pose_state as B,arm_shape_project as P
from lumaretouch_engine import creative_derived_body_export as X
from lumaretouch_engine import creative_derived_source as D,people_state as PEOPLE
from lumaretouch_engine import local_mask_state as LM
from lumaretouch_engine.creative_document_assets import make_asset


def base(width=4,height=4,value=0.):
    rgba=np.full((height,width,4),value,dtype='<f4');rgba[...,3]=1.
    return make_asset('rgba',width,height,rgba.tobytes(),original=b'provenance')


def bank(frame):
    points=[{'index':i,'x':.5,'y':.5,'z':0.,'visibility':0.,'presence':0.} for i in range(33)]
    record=E.create(source_frame=frame,values=points,backend_version='test-fixture',
        backend_code_sha256='b'*64,model_id='synthetic-unit-test-only',
        model_sha256='c'*64,input_rgb_sha256='d'*64,input_dimensions=(4,4))
    run={'source':frame,'records':[record],'detector_limit':4,'limit_reached':False,'census_complete':False}
    return B.add_run(B.empty(),run)


def setup(tmp_path,*,derived=True):
    path=tmp_path/'original.bin';path.write_bytes(b'physical-original')
    asset=base();state={'_creative_base':asset} if derived else {}
    source=D.binding(state) if derived else {'sha256':LM.source_digest(str(path)),'width':4,'height':4}
    state['_body_pose_bank']=P.pack(bank(R.source(source)))
    graph=PEOPLE.empty()
    # Deliberately another live document. Capture must use frozen state/graph.
    engine=SimpleNamespace(_creative_base=base(value=.25),_people_support={},
        _people_owner=lambda:SimpleNamespace(snapshot=lambda:graph))
    snap={'creative_base':asset if derived else None,'people':None}
    return engine,state,snap,str(path),source,graph


def test_capture_uses_frozen_target_not_other_live_document(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path)
    assert D.binding(engine)!=source
    R.capture(engine,snap,state,path,graph)
    assert snap['body_pose']['source']==R.source(source)
    assert snap['people']['creative_source']==source
    assert snap['people']['asset_sha256']==source['sha256']
    proof=X.verify_snapshot(snap,path)
    assert proof['original_sha256']==LM.source_digest(path)
    assert proof['asset_sha256']!=proof['original_sha256']


@pytest.mark.parametrize('mutation',['valid_other_content','valid_other_extent','invalid_id','missing_proof','proof_extent','body_extent'])
def test_changed_canonical_or_owned_body_identity_is_refused(tmp_path,mutation):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    if mutation=='valid_other_content':snap['creative_base']=base(value=.25)
    elif mutation=='valid_other_extent':snap['creative_base']=base(width=5)
    elif mutation=='invalid_id':snap['creative_base']['id']='sha256:'+'f'*64
    elif mutation=='missing_proof':snap.pop('body_pose_source_proof')
    elif mutation=='proof_extent':snap['body_pose_source_proof']['creative_source']['width']=5
    else:snap['body_pose']['source']['width']=5
    with pytest.raises(ValueError):X.verify_snapshot(snap,path)


def test_changed_original_provenance_is_not_relabelled_as_composite(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    before=LM.file_stamp(path)
    (tmp_path/'original.bin').write_bytes(b'changed-physical-original')
    with pytest.raises(ValueError):X.verify_snapshot(snap,path)
    with pytest.raises(ValueError):R.check_export_decode(snap,path,before,(4,4))


def test_decode_and_render_verify_effective_extent_and_original_stamp(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    before=LM.file_stamp(path)
    with pytest.raises(ValueError):R.check_export_decode(snap,path,before,(5,4))
    R.check_export_decode(snap,path,before,(4,4))
    spec=SimpleNamespace(creative_base=snap['creative_base'],people=snap['people'])
    R.configure_export(spec,snap,(4,4),for_document=True)
    assert spec.body_pose_source_proof==snap['body_pose_source_proof']
    assert spec.body_pose_source_path==path  # provenance, not derived model input
    R.verify_render_source(spec)
    spec.creative_base=base(value=.25)
    with pytest.raises(ValueError):R.verify_render_source(spec)


def test_original_source_keeps_legacy_decode_contract(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path,derived=False)
    R.capture(engine,snap,state,path,graph)
    assert snap['body_pose_source_proof'] is None
    assert 'creative_source' not in snap['people']
    assert X.verify_snapshot(snap,path) is None
    R.check_export_decode(snap,path,LM.file_stamp(path),(4,4))
    spec=SimpleNamespace(creative_base=None,people=snap['people'])
    R.configure_export(spec,snap,(4,4),for_document=True)
    R.verify_render_source(spec)
    snap['body_pose_source_proof']={'asset_sha256':source['sha256'],
        'creative_source':source,'original_sha256':source['sha256']}
    with pytest.raises(ValueError):X.verify_snapshot(snap,path)


def test_body_snapshot_cannot_transfer_to_another_document(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    R.check_export_decode(snap,path,LM.file_stamp(path),(4,4))
    spec=SimpleNamespace(creative_base=snap['creative_base'],people=snap['people'])
    with pytest.raises(ValueError):R.configure_export(spec,snap,(4,4),for_document=False)


def test_dormant_other_source_census_cannot_hide_in_frozen_bank(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path)
    retained=P.unpack(state['_body_pose_bank'])
    retained['analysis_runs']['f'*64]={'detector_limit':4,'limit_reached':False,'census_complete':False}
    state['_body_pose_bank']=P.pack(retained)
    with pytest.raises(ValueError):R.capture(engine,snap,state,path,graph)


def test_original_capture_still_rejects_wrong_physical_source(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path,derived=False)
    (tmp_path/'original.bin').write_bytes(b'a-different-original')
    with pytest.raises(ValueError):R.capture(engine,snap,state,path,graph)


def test_ephemeral_export_boundary_fence_rejects_unstamped_or_changed_pixels(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    R.check_export_decode(snap,path,LM.file_stamp(path),(4,4))
    spec=SimpleNamespace(creative_base=snap['creative_base'],people=snap['people'])
    R.configure_export(spec,snap,(4,4),for_document=True)
    pixels=np.zeros((4,4,3),np.float32)
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)
    # Synthetic exporter boundary only, not a claim that native decode ran.
    X.stamp_pixels(spec,pixels);X.verify_pixels(spec,pixels)
    pixels[0,0,0]=.001
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)
    with pytest.raises(ValueError):X.stamp_pixels(spec,pixels.astype(np.float64))
    pixels[0,0,0]=1.01
    with pytest.raises(ValueError):X.stamp_pixels(spec,pixels)


def test_row_hash_accepts_same_noncontiguous_pixels_without_full_copy(tmp_path):
    engine,state,snap,path,source,graph=setup(tmp_path);R.capture(engine,snap,state,path,graph)
    spec=SimpleNamespace(creative_base=snap['creative_base'],body_pose=snap['body_pose'],
        body_pose_source_proof=snap['body_pose_source_proof'])
    pixels=np.zeros((4,4,3),np.float32);X.stamp_pixels(spec,pixels)
    storage=np.zeros((4,8,3),np.float32)
    X.verify_pixels(spec,storage[:,::2,:])
    assert '_creative_body_resolved_pixels' not in snap
