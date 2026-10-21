import json
import os
from dataclasses import fields
import numpy as np
import pytest
from lumaretouch_engine.render_snapshot import own_render_inputs
from lumaretouch_engine.inspection_bundle import BundleWriter, read_bundle
from lumaretouch_engine.vram import RepairOp, LightOp
from lumaretouch_engine.face import FacePrecompute
from lumaretouch_engine.ops.lut import CubeLut


def write(tmp_path, value, quantum=7):
    owned = own_render_inputs(value, max_asset_bytes=1024*1024)
    writer = BundleWriter(tmp_path, owned)
    for _ in range(10000):
        if writer.advance(quantum):
            return writer
    pytest.fail('Bundle writer failed to make bounded progress')


def test_all_record_fields_and_numeric_layouts_roundtrip(tmp_path):
    face = FacePrecompute(np.zeros((2,3),np.float32), {'skin':np.ones((2,2),np.float32)},
                          'fixture',1.,2.,all_landmarks=[np.ones((2,3),np.float32)],
                          notes=['test'], manual=(0,))
    cube = CubeLut('1d',2,np.zeros((2,3),np.float64))
    value = {'repair':RepairOp(7,np.ones((2,3),np.uint8),{'radius':3}),
             'light':LightOp(8,np.zeros((2,3),np.uint8),-1),'face':face,'lut':cube,
             'scalar':np.array(3.,dtype='>f8'), 'empty':np.zeros((0,3),np.uint8),
             'list':[None, True, '汉字', -(2**63)], 'tuple':(1,.3)}
    write(tmp_path,value)
    out = read_bundle(tmp_path,max_asset_bytes=1024*1024)
    for key in ('repair','light','face','lut'):
        assert type(out[key]) is type(value[key])
        assert set(vars(out[key])) == {f.name for f in fields(value[key])}
    np.testing.assert_array_equal(out['face'].all_landmarks[0],face.all_landmarks[0])
    np.testing.assert_array_equal(out['repair'].weight,value['repair'].weight)
    assert not out['repair'].weight.flags.writeable
    assert out['scalar'].dtype == np.dtype('>f8') and out['scalar'].shape == ()
    assert out['empty'].shape == (0,3) and out['tuple'] == (1,.3)
    assert out['list'] == value['list']


def test_manifest_is_ticked_and_not_published_early(tmp_path):
    owned = own_render_inputs({'text':'x'*1000},max_asset_bytes=0)
    writer = BundleWriter(tmp_path,owned)
    writer.advance(7)
    assert not writer.done and not (tmp_path/'manifest.json').exists()
    assert (tmp_path/'manifest.part').stat().st_size == 7
    writer.cancel()
    assert not (tmp_path/'manifest.json').exists()
    with pytest.raises(ValueError,match='cancelled'):
        writer.advance(7)


def test_cancel_releases_array_references(tmp_path):
    owned = own_render_inputs({'a':np.ones(100,np.uint8)},max_asset_bytes=100)
    writer = BundleWriter(tmp_path,owned)
    writer.advance(9)
    assert writer.written_bytes == 9
    writer.cancel(); writer.cancel()
    assert writer._arrays == [] and writer._file is None


def test_payload_budget_rejected_before_allocation(tmp_path,monkeypatch):
    write(tmp_path,{'a':np.ones(10,np.uint8)})
    monkeypatch.setattr(np,'empty',lambda *a,**k:pytest.fail('Allocated before admission'))
    with pytest.raises(ValueError):
        read_bundle(tmp_path,max_asset_bytes=9)


@pytest.mark.parametrize('mutation', ['offset','dtype','shape','reference','record','trailing'])
def test_corrupt_bundle_is_rejected_before_array_allocation(tmp_path,monkeypatch,mutation):
    write(tmp_path,{'a':RepairOp(1,np.ones(10,np.uint8))})
    path = tmp_path/'manifest.json'; m = json.loads(path.read_text())
    if mutation == 'offset': m['arrays'][0]['offset'] = 1
    elif mutation == 'dtype': m['arrays'][0]['dtype'] = '|O'
    elif mutation == 'shape': m['arrays'][0]['shape'] = [2**31]
    elif mutation == 'reference': m['tree'] = ['dict',[['a',['array',0]],['b',['array',0]]]]
    elif mutation == 'record': m['tree'][1][0][1][1] = '__import__'
    elif mutation == 'trailing':
        with open(tmp_path/'arrays.bin','ab') as f: f.write(b'x')
    path.write_text(json.dumps(m))
    monkeypatch.setattr(np,'empty',lambda *a,**k:pytest.fail('Allocated before validation'))
    with pytest.raises(ValueError): read_bundle(tmp_path,max_asset_bytes=100)


@pytest.mark.parametrize('kind',['fifo','symlink'])
def test_nonregular_manifest_rejected_without_blocking(tmp_path,kind):
    path = tmp_path/'manifest.json'
    if kind == 'fifo': os.mkfifo(path)
    else: path.symlink_to(tmp_path/'elsewhere')
    with pytest.raises((ValueError,OSError)):
        read_bundle(tmp_path,max_asset_bytes=100)


def test_record_key_accounting_matches_reader(tmp_path,monkeypatch):
    from lumaretouch_engine import inspection_bundle as bundle
    value = {'op':LightOp(1,np.ones(1,np.uint8),1)}
    # root + outer key + record + 3 record keys + 3 values = 9 nodes.
    monkeypatch.setattr(bundle,'MAX_NODES',9)
    write(tmp_path,value)
    assert read_bundle(tmp_path,max_asset_bytes=1)['op'].sign == 1
    other = tmp_path/'too-small'; other.mkdir()
    monkeypatch.setattr(bundle,'MAX_NODES',8)
    with pytest.raises(ValueError,match='structure'):
        write(other,value)
