"""Geometry contract tests, not a claim that real-photo segmentation is correct."""
import numpy as np
import pytest
from lumaretouch_engine.face_scope import selected_face_skin,FACE_OVAL,BROW_LEFT,BROW_RIGHT,LIPS
from lumaretouch_engine.ops.enhance import EYE_RING_LEFT,EYE_RING_RIGHT


def face(cx=.35,cy=.5,rx=.22,ry=.38):
    lm=np.zeros((478,3),np.float32);lm[:,:2]=[cx,cy]
    def oval(ids,x,y,a,b):
        theta=np.linspace(-np.pi/2,3*np.pi/2,len(ids),endpoint=False)
        lm[list(ids),:2]=np.stack([x+a*np.cos(theta),y+b*np.sin(theta)],axis=1)
    oval(FACE_OVAL,cx,cy,rx,ry)
    oval(EYE_RING_LEFT,cx-rx*.4,cy-ry*.2,rx*.17,ry*.07)
    oval(EYE_RING_RIGHT,cx+rx*.4,cy-ry*.2,rx*.17,ry*.07)
    oval(LIPS,cx,cy+ry*.5,rx*.25,ry*.09)
    oval(BROW_LEFT,cx+rx*.4,cy-ry*.4,rx*.2,ry*.045)
    oval(BROW_RIGHT,cx-rx*.4,cy-ry*.4,rx*.2,ry*.045)
    return lm


def test_scope_excludes_background_features_and_other_face():
    base=np.ones((400,500),np.float32);a=face();b=face(cx=.75)
    got=selected_face_skin(base,a,other_landmarks=[b])
    assert np.any(got>0) and got.dtype==np.float32
    assert not np.any(got[:,300:]) and not np.any(got[:30])
    for ids in [EYE_RING_LEFT,EYE_RING_RIGHT,LIPS,BROW_LEFT,BROW_RIGHT]:
        x,y=a[list(ids),:2].mean(axis=0)*[500,400]
        assert got[int(y),int(x)]==0
    x,y=b[list(FACE_OVAL),:2].mean(axis=0)*[500,400]
    assert got[int(y),int(x)]==0
    np.testing.assert_array_equal(base,np.ones_like(base))


def test_semantic_holes_never_reintroduced_and_weights_never_increased():
    rng=np.random.default_rng(22);base=rng.random((120,160),dtype=np.float32);base[::3,::4]=0
    got=selected_face_skin(base,face())
    assert np.all(got<=base) and np.all(got>=0)
    assert not np.any(got[base==0])
    np.testing.assert_array_equal(got,selected_face_skin(base,face()))


def test_switching_selection_does_not_mutate_shared_base():
    base=np.ones((300,500),np.float32);a=face(cx=.25,rx=.18);b=face(cx=.75,rx=.18)
    left=selected_face_skin(base,a,other_landmarks=[b]);right=selected_face_skin(base,b,other_landmarks=[a])
    assert np.any(left[:,:250]) and not np.any(left[:,250:])
    assert np.any(right[:,250:]) and not np.any(right[:,:250])
    assert np.all(base==1)


@pytest.mark.parametrize('bad',[np.full((40,40),np.nan),np.full((40,40),-1),np.full((40,40),2),np.ones((4,4,3))])
def test_invalid_semantic_input_fails_closed(bad):
    with pytest.raises(ValueError):selected_face_skin(bad,face())


def test_degenerate_landmarks_do_not_expand_to_whole_image():
    with pytest.raises(ValueError):selected_face_skin(np.ones((40,40)),np.zeros((478,3)))


def test_real_two_face_geometry_keeps_other_face_and_features_unchanged():
    pytest.importorskip('torch');mp=pytest.importorskip('mediapipe')
    from PIL import Image
    from pathlib import Path
    from lumaretouch_engine.face import MediaPipeFace
    from lumaretouch_engine.semantic_masks import skin_from_multiclass,skin_edit_weight
    from lumaretouch_engine.export import export_image,ExportSpec
    one=np.asarray(Image.open(Path(__file__).parent/'fixtures/nasa-astronaut-face-crop.png').convert('RGB'))
    h,w=one.shape[:2];gap=30
    source=np.zeros((h,2*w+gap,3),np.uint8);source[:,:w]=one;source[:,w+gap:]=one[:,::-1]
    with MediaPipeFace() as backend:
        pc=backend(source)
        assert pc.num_faces==2
        _,segmenter=backend._ensure()
        outputs=segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,data=source))
        masks=[np.array(x.numpy_view(),copy=True) for x in outputs.confidence_masks]
        skin_from_multiclass(masks)  # Validate class contract before accessing class3.
        face_probability=masks[3][...,0] if masks[3].ndim==3 else masks[3]
        face_weight=skin_edit_weight(face_probability)
    left,right=sorted(pc.all_landmarks,key=lambda x:float(x[:,0].mean()))
    scoped=selected_face_skin(face_weight,left,other_landmarks=[right])
    assert np.count_nonzero(scoped)>100
    assert not np.any(scoped[:,w:])
    for ids in [EYE_RING_LEFT,EYE_RING_RIGHT,LIPS,BROW_LEFT,BROW_RIGHT]:
        x,y=left[list(ids),:2].mean(axis=0)*[source.shape[1],h]
        assert scoped[int(y),int(x)]==0
    spec=ExportSpec(strength=.6,radius=3,texture_radius=2,channel='face_skin',
                    masks=scoped[None],mask_names=['face_skin'],landmarks=left)
    got,_=export_image(source,spec,device='cpu',tile=256)
    assert np.any(got!=source)
    np.testing.assert_array_equal(got[scoped==0],source[scoped==0])
    np.testing.assert_array_equal(got[:,w:],source[:,w:])
