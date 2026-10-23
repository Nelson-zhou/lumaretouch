"""AUTHORED / UNRUN: derived sky provenance/export/consumer boundaries."""
from types import SimpleNamespace
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import sky_replacement_runtime as R
from lumaretouch_engine import sky_replacement_state as S
from lumaretouch_engine import creative_derived_sky as C


def disabled():
    result=S.empty();result['source']={'sha256':'a'*64,'width':12,'height':8}
    result['parameters']['brightness']=10
    return result


def test_physical_decode_dimensions_are_not_returned_source_grid(monkeypatch):
    snap={'creative_base':object(),'sky_replacement':disabled(),'creative_sky_context':object()}
    stamp=(1,2,3,4,5);seen=[]
    monkeypatch.setattr(R.B,'file_stamp',lambda path:stamp)
    monkeypatch.setattr(C,'verify_snapshot',lambda snapshot,path=None,shape=None:seen.append((path,shape)))
    R.check_export_decode(snap,'original.png',stamp,(300,400))
    assert seen==[('original.png',None)] and snap['sky_replacement_stamp']==list(stamp)


def test_retained_disabled_context_still_checks_original_provenance(monkeypatch):
    snap={'creative_base':object(),'sky_replacement':disabled(),'creative_sky_context':object()}
    monkeypatch.setattr(R.B,'file_stamp',lambda path:(9,2,3,4,5))
    with pytest.raises(ValueError):R.check_export_decode(snap,'original.png',(1,2,3,4,5),(300,400))
    assert 'sky_replacement_path' not in snap


def test_disabled_retained_context_cannot_transfer_to_another_photo():
    with pytest.raises(ValueError):
        R.configure_export(SimpleNamespace(),{'creative_base':object(),'sky_replacement':disabled(),
            'creative_sky_context':object()},(8,12),for_document=False)


def test_canonical_pixels_verified_before_any_sky_prepare(monkeypatch):
    value=disabled();value['enabled']=True
    spec=SimpleNamespace(creative_base=object(),sky_replacement=value,
        sky_replacement_path='original.png',sky_replacement_stamp=[1,2,3,4,5])
    monkeypatch.setattr(R.S,'check',lambda v:deepcopy(v))
    monkeypatch.setattr(R.B,'file_stamp',lambda path:(1,2,3,4,5))
    prepared=[]
    monkeypatch.setattr(R,'prepare',lambda *a,**k:prepared.append('called'))
    def reject(*args):raise ValueError('changed canonical pixels')
    monkeypatch.setattr(C,'verify_export',reject)
    with pytest.raises(ValueError,match='canonical'):
        R.export_prepare(spec,(8,12),source_pixels=np.zeros((8,12,3),np.float32))
    assert prepared==[]


def test_full_sky_recovery_retains_current_edits_exactly():
    torch=pytest.importorskip('torch')
    from lumaretouch_engine.ops.sky_replacement import compose
    current=torch.full((1,3,2,2),.4)
    masks={key:torch.ones((1,1,2,2)) if key in ('sky','recovery') else torch.zeros((1,1,2,2))
        for key in ('sky','person','water','recovery')}
    result=compose(current,torch.full_like(current,.9),torch.full_like(current,.8),
        torch.ones((1,3,1,1)),masks,S.defaults(),horizon_weight=1.,align=lambda v:v)
    assert torch.equal(result,current)
