"""Each RGB16 output must apply its own frozen recipe, never silently pass through edits."""
import numpy as np
import pytest
import tifffile
from test_protocol import engine,_wait_frame_mode,_collect_until
from lumaretouch_engine.export import read_tiff16,export_image16,ExportSpec


def test_other_image_edits_use_its_own_rgb16_recipe(engine,tmp_path):
    pytest.importorskip('torch')
    a,b=tmp_path/'a.tif',tmp_path/'b.tif'
    ramp=np.arange(64*80*3,dtype=np.uint16).reshape(64,80,3)*3+7
    other=np.flip(ramp,axis=1).copy()
    tifffile.imwrite(a,ramp,photometric='rgb');tifffile.imwrite(b,other,photometric='rgb')
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(b),strength=0);engine.wait_for('image_ready',timeout=60)
    engine.send(cmd='exposure',ev=.37);_wait_frame_mode(engine,'exposure')
    engine.send(cmd='load_image',path=str(a),strength=0);engine.wait_for('image_ready',timeout=60)
    engine.send(cmd='export',images=[str(a),str(b)],out_dir=str(tmp_path/'out'),format='tif',bit_depth=16)
    done,_=_collect_until(engine,'export_done')
    assert done['failed']==0 and done['total']==2,done
    results={x['path']:x for x in done['images']}
    np.testing.assert_array_equal(read_tiff16(results[str(a)]['out']),ramp)
    expected,_=export_image16(other,ExportSpec(strength=0,exposure=(.37,0,0,0,0,0,0)),device='cpu')
    np.testing.assert_array_equal(read_tiff16(results[str(b)]['out']),expected)
    assert np.any(expected!=other)
    assert results[str(a)]['pipeline']=='passthrough_rgb16'
    assert results[str(b)]['pipeline']=='float32_rgb16'
    assert results[str(b)]['bits']==16 and results[str(b)]['readback_max_diff']==0
