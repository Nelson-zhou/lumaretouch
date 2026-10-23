"""AUTHORED / UNRUN: derived iris-reference source and crop contracts.

Synthetic landmarks/pixels are contract fixtures, not inference or visual QA.
No product imports, tests or native rendering were run while authoring.
"""
import base64
import hashlib
import io
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image
from lumaretouch_engine import creative_derived_source as D, people_state as P
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.iris_makeup_reference import acquire


def fixture(monkeypatch,radius=12.):
    rgba=np.zeros((128,128,4),dtype='<f4');rgba[...,3]=1.
    base=make_asset('rgba',128,128,rgba.tobytes())
    source=D.binding({'_creative_base':base})
    lm=np.zeros((478,3),dtype='<f4');lm[:,:2]=.5
    for center,ring,x in ((468,(469,470,471,472),40.),(473,(474,475,476,477),88.)):
        lm[center,:2]=[x/127.,64/127.]
        for index,(dx,dy) in zip(ring,((radius,0),(0,radius),(-radius,0),(0,-radius))):
            lm[index,:2]=[(x+dx)/127.,(64+dy)/127.]
    lm[33,:2]=[20/127.,64/127.];lm[133,:2]=[60/127.,64/127.]
    lm[263,:2]=[68/127.,64/127.];lm[362,:2]=[108/127.,64/127.]
    evidence={'backend':'mediapipe','status':'verified','detector_model_sha256':'1'*64,
        'semantic_model_sha256':'2'*64,'landmark_digest':hashlib.sha256(lm.tobytes()).hexdigest(),
        'source_width':128,'source_height':128,'orientation':'exif_normalized_once'}
    face=P.new_face(source['sha256'],[.05,.05,.95,.95],evidence)
    state=P.empty();state['faces'][face['face_instance_id']]=face;ref=P.face_ref(face)
    rgb=np.empty((128,128,3),dtype=np.uint8);rgb[:]=[63,127,191];rgb.setflags(write=False)
    # Excluded may be absent while genuine skin support still exists. The crop
    # must check that skin against actual RGB dimensions, never guessed (0,0).
    analysis={'face_ref':ref,'evidence':deepcopy(evidence),'landmarks':lm,
              'excluded':None,'skin':np.ones((128,128),dtype=np.float32)}
    pc=SimpleNamespace(backend='mediapipe',masks={'skin':analysis['skin']})
    engine=SimpleNamespace(_creative_base=base,_src_rgb=np.zeros_like(rgb),_precompute=pc,
        _people_source=lambda:deepcopy(source),
        _people_owner=lambda:SimpleNamespace(snapshot=lambda:deepcopy(state)),
        _people_analyses={source['sha256']:{ref['face_instance_id']:analysis}})
    monkeypatch.setattr(D,'analysis_rgb',lambda _:rgb)
    D.stamp_precompute(engine,pc,rgb)
    return engine,source,ref,state,analysis,rgb


def test_crop_contains_derived_not_original_pixels_and_does_not_enlarge(monkeypatch):
    engine,source,ref,_,_,rgb=fixture(monkeypatch)
    result=acquire(engine,source,ref)
    image=Image.open(io.BytesIO(base64.b64decode(result['base64'])))
    pixels=np.asarray(image)
    assert np.all(pixels==[63,127,191]) and np.any(pixels!=0)
    assert result['source']==source and result['mapping']=='source_pixel_centre_eye_crop'
    assert image.size==(result['width'],result['height'])
    assert result['width']<=rgb.shape[1] and result['height']<=rgb.shape[0]
    assert result['minimum_iris_radius']>=8
    assert result['view_box'][2:]==[float(image.width),float(image.height)]


@pytest.mark.parametrize('change',[
    lambda engine: setattr(engine,'_precompute',None),
    lambda engine: setattr(engine._precompute,'backend','synthetic'),
    lambda engine: engine._precompute.input_source_binding.update(sha256='a'*64),
    lambda engine: engine._precompute.input_source_binding.update(proxy_sha256='a'*64),
])
def test_missing_or_foreign_inference_proof_is_refused(monkeypatch,change):
    engine,source,ref,_,_,_=fixture(monkeypatch);change(engine)
    with pytest.raises(ValueError):acquire(engine,source,ref)


def test_foreign_or_stale_ref_is_not_relabelled(monkeypatch):
    engine,source,ref,_,_,_=fixture(monkeypatch)
    wrong=deepcopy(ref);wrong['analysis_revision']+=1
    with pytest.raises(ValueError):acquire(engine,source,wrong)
    wrong=deepcopy(ref);wrong['asset_sha256']='b'*64
    with pytest.raises(ValueError):acquire(engine,source,wrong)
    with pytest.raises(ValueError):acquire(engine,{**source,'width':256},ref)


def test_all_semantic_masks_are_checked_against_actual_rgb_extent(monkeypatch):
    engine,source,ref,_,analysis,_=fixture(monkeypatch)
    analysis['excluded']=np.zeros((16,16),dtype=np.float32)
    with pytest.raises(ValueError,match='source frame'):acquire(engine,source,ref)


def test_landmark_bytes_cannot_change_without_matching_evidence(monkeypatch):
    engine,source,ref,_,analysis,_=fixture(monkeypatch)
    analysis['landmarks']=analysis['landmarks'].copy();analysis['landmarks'][468,0]+=.01
    with pytest.raises(ValueError,match='landmark bytes'):acquire(engine,source,ref)


def test_minimum_actual_iris_detail_remains_required(monkeypatch):
    engine,source,ref,_,_,_=fixture(monkeypatch,radius=2.)
    with pytest.raises(ValueError,match='虹膜像素不足'):acquire(engine,source,ref)


def test_face_change_during_crop_preparation_is_refused(monkeypatch):
    engine,source,ref,state,_,_=fixture(monkeypatch);calls=[]
    changed=deepcopy(state);changed['faces'][ref['face_instance_id']]['enabled']=False
    def snapshot():
        calls.append(True)
        return deepcopy(state if len(calls)==1 else changed)
    engine._people_owner=lambda:SimpleNamespace(snapshot=snapshot)
    with pytest.raises(ValueError,match='准备期间人物分析改变'):acquire(engine,source,ref)
