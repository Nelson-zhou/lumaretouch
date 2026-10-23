"""AUTHORED / UNRUN: studio integration, provenance and inference ordering."""
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import studio_background_state as S
from lumaretouch_engine import studio_background_runtime as R
from lumaretouch_engine import studio_background_export as E
from lumaretouch_engine import creative_derived_studio as D
from lumaretouch_engine import creative_smoothing_host as H


def value():
    result=S.empty()
    result['source']={'sha256':'a'*64,'width':12,'height':8}
    result['parameters']['enhancement']=.25
    return result


def test_original_decode_grid_is_only_provenance(monkeypatch):
    snap={'creative_base':object(),'studio_background':value()}
    stamp=(1,2,3,4,5);calls=[]
    monkeypatch.setattr(R.M,'file_stamp',lambda path:stamp)
    monkeypatch.setattr(D,'verify_snapshot',lambda snapshot,path=None,shape=None:calls.append((path,shape)))
    R.check_export_decode(snap,'original.png',stamp,(300,400))
    assert calls==[('original.png',None)]
    assert snap['studio_background_stamp']==list(stamp)


def test_provenance_change_rejects_before_binding(monkeypatch):
    snap={'creative_base':object(),'studio_background':value()}
    monkeypatch.setattr(R.M,'file_stamp',lambda path:(9,2,3,4,5))
    with pytest.raises(ValueError):R.check_export_decode(snap,'original.png',(1,2,3,4,5),(300,400))
    assert 'studio_background_path' not in snap


def test_studio_cannot_transfer_vectors_to_another_document():
    with pytest.raises(ValueError):
        R.configure_export(SimpleNamespace(),{'studio_background':value()},(8,12),for_document=False)


def test_canonical_pixels_checked_before_model_observation(monkeypatch):
    spec=SimpleNamespace(studio_background=value(),creative_base=object())
    called=[]
    monkeypatch.setattr(E,'check_spec',lambda spec:None)
    def reject(spec,pixels):raise ValueError('wrong canonical pixels')
    monkeypatch.setattr(D,'verify_export',reject)
    monkeypatch.setattr(E,'full_semantic',lambda *args:called.append('model'))
    with pytest.raises(ValueError,match='canonical'):
        E.prepare_export(spec,np.zeros((8,12,3),np.float32))
    assert called==[]


def test_semantic_studio_reopens_without_retained_faces():
    studio=value();studio['region_mode']='semantic_background'
    studio['semantic_owner']={'backend':'mediapipe','contract':'mediapipe-selfie-multiclass-six-classes-v1:'+'b'*64}
    engine=SimpleNamespace(_creative_base=object(),_studio_background=studio,
        _strength=0.,_channel=None,_fabric_amount=0.)
    assert H.needs_analysis(engine)
    engine._creative_base=None
    assert not H.needs_analysis(engine)


def test_studio_recovery_uses_current_operator_input_not_original_pixels():
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.studio_background_stage import StudioBackgroundStage
    stage=StudioBackgroundStage('cpu',(2,2))
    stage.recovery['intrusions']=torch.tensor([[[[0.,1.],[.5,1.]]]])
    current=torch.full((1,3,2,2),.4)  # Already includes other edits.
    after=current+.2
    restored=stage._recover('intrusions',current,after)
    assert torch.equal(restored[:,:,:,1],current[:,:,:,1])
    assert torch.equal(restored[:,:,0,0],after[:,:,0,0])
    assert torch.allclose(restored[:,:,1,0],torch.full((1,3),.5))
