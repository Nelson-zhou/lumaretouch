"""Invalid import parameters must not decode or switch the current document."""
import pytest
from lumaretouch_engine import server, decode


@pytest.mark.parametrize('value', ['bad', float('nan'), float('inf'), -float('inf')])
def test_nonfinite_or_invalid_strength_cannot_enter_state(value):
    with pytest.raises((ValueError, TypeError)):
        server._clamp_strength(value)


@pytest.mark.parametrize('value', ['bad', float('nan'), float('inf')])
def test_bad_import_strength_is_checked_before_decode(monkeypatch, value):
    engine = server.Engine('test-import-validation')
    decoded = []
    def no_decode(*a, **kw):
        decoded.append(a)
        raise RuntimeError('decode must not be reached')
    events = []
    monkeypatch.setattr(decode, 'load_rgb', no_decode)
    monkeypatch.setattr(server, 'emit', events.append)
    before = (engine._doc_path, engine._doc_index, list(engine._docs), engine._strength)
    try:
        engine.cmd_load_image({'path': 'not-a-real-file.png', 'strength': value})
    except (ValueError, TypeError):
        pass  # the JSON dispatcher converts this to an error event
    assert not decoded
    assert (engine._doc_path, engine._doc_index, engine._docs, engine._strength) == before


@pytest.mark.parametrize('value,expected', [(-2,0.),(2,1.),(.35,.35)])
def test_finite_clamping_contract_is_unchanged(value,expected):
    assert server._clamp_strength(value) == expected

from test_protocol import engine
from PIL import Image


def test_invalid_import_preserves_active_document_and_recipe_over_ipc(engine,tmp_path):
    pytest.importorskip('torch')
    a,b=tmp_path/'a.png',tmp_path/'b.png'
    Image.new('RGB',(64,64),'red').save(a)
    Image.new('RGB',(64,64),'blue').save(b)
    engine.send(cmd='hello');engine.wait_for('ready')
    engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
    engine.send(cmd='load_image',path=str(a),strength=.4)
    engine.wait_for('image_ready',timeout=30)
    engine.wait_for('session_state',timeout=30)
    engine.send(cmd='session',action='state')
    before=engine.wait_for('session_state',timeout=30)
    for value in ['bad',float('nan'),float('inf')]:
        engine.send(cmd='load_image',path=str(b),strength=value)
        engine.wait_for('error',timeout=30)
        engine.send(cmd='session',action='state')
        after=engine.wait_for('session_state',timeout=30)
        assert after['index']==before['index']
        assert after['docs']==before['docs']
    engine.send(cmd='set_strength',value=.4)
    assert engine.wait_for('params_set',timeout=30)['strength']==.4
