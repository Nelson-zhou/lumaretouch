"""Scalar edits must not overwrite unrelated values from a stale UI snapshot."""
from types import SimpleNamespace
from unittest.mock import patch
from lumaretouch_engine.server import Engine


def test_radius_patch_preserves_strength_and_other_bands():
    e=Engine.__new__(Engine)
    e._image_loaded=True;e.bench=None;e._strength=.7;e._channel=None
    e.shm=SimpleNamespace(w=10,h=10)
    e._vram=SimpleNamespace(w=10,h=10,mask_names=['skin'],last_filter_ms=0,last_bands_ms=0,last_light_ms=0)
    e._params={'radius':12,'eps':.0006,'texture_radius':4,'detail_gain':1.2,'mid_gain':.2,'broad_gain':.3}
    e._write_current_frame=lambda mode:{'event':'frame','render_ms':0}
    events=[]
    with patch('lumaretouch_engine.server.emit',events.append):
        e.cmd_set_strength({'cmd':'set_strength','radius':20,'channel':'skin'})
    assert e._strength==.7
    assert e._channel=='skin'
    assert e._params=={'radius':20,'eps':.0006,'texture_radius':4,'detail_gain':1.2,'mid_gain':.2,'broad_gain':.3}
    assert [v['event'] for v in events]==['params_set','frame']
