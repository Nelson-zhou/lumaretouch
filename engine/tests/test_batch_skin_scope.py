from types import SimpleNamespace
import numpy as np
import pytest
from test_export_per_image_recipe import _mk_session,_batch_snap
from lumaretouch_engine import server,face,decode
from lumaretouch_engine.export import ExportError


def test_missing_per_image_skin_never_falls_back_to_global():
    snap=_batch_snap();snap['channel']='skin'
    with pytest.raises(ExportError,match='全图'):
        _mk_session([])._export_snapshot(snap,100,120,for_document=False)


def test_bare_image_gets_own_analysis_without_copying_coordinates(monkeypatch):
    snap=_batch_snap();snap.update(channel='skin',precompute=object(),repair_ops=[object()])
    rgb=np.full((12,16,3),55,np.uint8);calls=[]
    monkeypatch.setattr(decode,'load_rgb',lambda path,**kw:(calls.append(path) or SimpleNamespace(rgb=rgb)))
    own=SimpleNamespace(masks={"skin":np.ones((12,16),np.float32)})
    class Backend:
        def __enter__(self):return self
        def __exit__(self,*args):calls.append('closed')
        def __call__(self,pixels):
            assert pixels is rgb
            return own
    monkeypatch.setattr(face,'MediaPipeFace',Backend)
    prepared,owned=_mk_session([])._prepare_export_snapshot('/different.tif',snap,False)
    assert owned and prepared['precompute'] is own
    assert prepared['repair_ops']==[] and prepared['deform']['amounts']=={}
    assert snap['precompute'] is not own and len(snap['repair_ops'])==1
    assert prepared['strength']==snap['strength'] and prepared['channel']=='skin'
    assert calls==['/different.tif','closed']


def test_existing_document_uses_its_own_cached_mask():
    snap=_batch_snap();snap.update(channel='skin',precompute=SimpleNamespace(masks={'skin':np.ones((12,16),np.float32)}))
    prepared,owned=_mk_session([])._prepare_export_snapshot('/same.tif',snap,True)
    assert prepared is snap and owned


def test_missing_targeted_face_is_not_silently_reselected():
    snap=_batch_snap();snap.update(channel='skin',precompute=None,deform={'amounts':{'slim_face':.4}})
    with pytest.raises(ExportError,match='选择人物'):
        _mk_session([])._prepare_export_snapshot('/same.tif',snap,True)


from pathlib import Path
from PIL import Image
from test_protocol import engine,_collect_until


def test_bare_photo_skin_export_reanalyzes_and_preserves_background(engine,tmp_path):
    pytest.importorskip('torch');pytest.importorskip('mediapipe')
    source=Path(__file__).parent/'fixtures/nasa-astronaut-face-crop.png'
    a=tmp_path/'a.png';b=tmp_path/'b.png'
    image=Image.open(source).convert('RGB');image.save(a)
    image.transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(b)
    original=np.array(Image.open(b).convert('RGB'))
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(a),strength=0);engine.wait_for('image_ready',timeout=60)
    engine.send(cmd='precompute',backend='mediapipe');engine.wait_for('precompute_ready',timeout=60)
    engine.send(cmd='set_strength',value=.6,channel='skin');engine.wait_for('params_set',timeout=30)
    engine.send(cmd='export',images=[str(a),str(b)],out_dir=str(tmp_path/'out'),format='png',tile=256)
    done,_=_collect_until(engine,'export_done')
    assert done['failed']==0 and done['total']==2,done
    item=next(x for x in done['images'] if x['path']==str(b))
    assert item['channel']=='skin'
    got=np.array(Image.open(item['out']).convert('RGB'))
    np.testing.assert_array_equal(got[:15,:20],original[:15,:20])
    np.testing.assert_array_equal(got[:15,-20:],original[:15,-20:])
    assert np.any(got!=original), 'preserving background cannot mean skipping all skin edits'


def test_empty_skin_is_not_reported_as_a_successful_edit():
    snap=_batch_snap();snap.update(channel='skin',precompute=SimpleNamespace(masks={'skin':np.zeros((12,16),np.float32)}))
    with pytest.raises(ExportError,match='空蒙版'):
        _mk_session([])._prepare_export_snapshot('/empty.tif',snap,True)
