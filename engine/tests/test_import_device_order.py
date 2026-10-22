"""Cold RAW previews precede GPU warmup, never replace editable source pixels."""
from unittest.mock import patch
from pathlib import Path
from lumaretouch_engine.server import Engine


def _order(tmp_path, *, loaded=False, raw=True, device=True, gpu_available=True, preview=True):
    engine = Engine.__new__(Engine)
    engine.bench = engine._export = None
    engine._image_loaded = loaded
    engine._proxy_budget = 4096
    engine._cuda = gpu_available
    engine.device = 'cpu'
    order = []
    def select(payload):
        order.append(('device', payload['device']))
        engine.device = 'cuda'
    engine.cmd_set_device = select
    engine._push_preview_frame = lambda path, budget, document_id: order.append(('preview', Path(path).name)) or ({'seq': 1} if preview else None)
    def decode(path, budget, *, device):
        order.append(('decode', device))
        raise ValueError('fixture stops before allocating a resident pipeline')
    # Keep the real source-identity stat boundary; only decoding is mocked.
    source = tmp_path / 'fixture.raw'
    source.write_bytes(b'import ordering fixture')
    payload = {'path': str(source)}
    if device:
        payload['device'] = 'auto'
    with patch('lumaretouch_engine.decode.is_raw', return_value=raw), \
         patch('lumaretouch_engine.decode.load_rgb', side_effect=decode), \
         patch('lumaretouch_engine.server.emit') as emit:
        engine.cmd_load_image(payload)
    assert emit.call_args.args[0]['event'] == 'error'
    assert 'fixture stops before allocating' in emit.call_args.args[0]['error']
    return order


def test_cold_raw_preview_precedes_device_selection_and_decode(tmp_path):
    assert _order(tmp_path) == [('preview', 'fixture.raw'), ('device', 'auto'), ('decode', 'cuda')]


def test_existing_session_migrates_before_preview_not_over_it(tmp_path):
    assert _order(tmp_path, loaded=True) == [('device', 'auto'), ('preview', 'fixture.raw'), ('decode', 'cuda')]


def test_non_raw_still_resolves_device_before_decode(tmp_path):
    assert _order(tmp_path, raw=False) == [('device', 'auto'), ('decode', 'cuda')]


def test_legacy_load_without_device_preserves_current_selection(tmp_path):
    assert _order(tmp_path, device=False) == [('preview', 'fixture.raw'), ('decode', 'cpu')]


def test_unavailable_requested_gpu_decodes_on_effective_cpu(tmp_path):
    assert _order(tmp_path, gpu_available=False)[-1] == ('decode', 'cpu')


def test_missing_embedded_preview_does_not_block_real_decode(tmp_path):
    assert _order(tmp_path, preview=False)[-2:] == [('device', 'auto'), ('decode', 'cuda')]


def test_invalid_budget_cannot_trigger_device_or_preview_side_effects():
    engine = Engine.__new__(Engine)
    engine.bench = engine._export = None
    engine._proxy_budget = 4096
    calls = []
    engine.cmd_set_device = lambda p: calls.append('device')
    engine._push_preview_frame = lambda *a: calls.append('preview')
    for budget in ['bad', float('inf'), -1, 9000000]:
        try:
            engine.cmd_load_image({'path': 'bad.raw', 'max_px': budget, 'device': 'auto'})
        except (ValueError, TypeError, OverflowError):
            pass
        else:
            raise AssertionError('invalid proxy budget accepted')
    assert calls == []
