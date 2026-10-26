"""AUTHORED / UNRUN: Original-native16 route regression and neutral pixel contract.

The route fixtures deliberately model an incomplete legacy classifier. They do
not claim numeric acceptance of active effects or full worker/codec execution.
The neutral fixture exercises the real canonical RGB16 renderer, intercepting
only final publication, and must be run locally with the existing dependencies.
"""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


OMITTED_EFFECTS = (
    'colour_grading', 'selective_colour', 'primary_calibration',
    'extended_tone', 'photo_detail', 'id_background',
)


def native16_route():
    source = Path(__file__).parents[1] / 'src/lumaretouch_engine/server.py'
    tree = ast.parse(source.read_text())
    worker = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == '_export_loop')
    matches = [n for n in ast.walk(worker) if isinstance(n, ast.If) and any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
        and call.func.attr == '_master16_snapshot_blockers'
        for call in ast.walk(n.test))]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize('codec', ['png', 'tif'])
@pytest.mark.parametrize('effects', [(name,) for name in OMITTED_EFFECTS] +
                         [OMITTED_EFFECTS, ()],
                         ids=[*OMITTED_EFFECTS, 'mixed', 'neutral'])
def test_original_native16_never_uses_legacy_neutral_shortcut(codec, effects):
    # Opaque markers are enough for the dispatch contract: no effect whitelist
    # may decide Original's route, even if all legacy blockers would be empty.
    snap = {name: {'active_fixture_marker': True} for name in effects}
    def forbidden(_snapshot):
        pytest.fail('Original consulted the incomplete legacy neutral classifier')
    guard = compile(ast.Expression(native16_route().test), '<native16-route>', 'eval')
    assert eval(guard, {'__builtins__': {}}, {
        'decision': {'codec': codec, 'bits': 16}, 'watermark': None,
        'self': SimpleNamespace(_master16_snapshot_blockers=forbidden),
        'snap_i': snap,
    }) is True


def test_original_native16_branch_keeps_decode_verification_and_full_recipe():
    route = native16_route()
    branch = ast.Module(body=route.body, type_ignores=[])
    calls = [n for n in ast.walk(branch) if isinstance(n, ast.Call)]
    assert any(isinstance(n.func, ast.Name) and n.func.id == 'verify_format_decode'
               for n in calls)
    assert any(isinstance(n.func, ast.Attribute) and n.func.attr == '_export_snapshot'
               for n in calls)
    decode = next(n for n in calls if isinstance(n.func, ast.Name) and n.func.id == 'load_full')
    want_bits = next(k.value for k in decode.keywords if k.arg == 'want_bits')
    assert isinstance(want_bits, ast.IfExp)
    assert isinstance(want_bits.body, ast.Constant) and want_bits.body.value == 16
    assignments = [n for n in ast.walk(branch) if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'render16' for t in n.targets)]
    assert len(assignments) == 1
    renderer = assignments[0].value
    assert isinstance(renderer, ast.IfExp)
    assert isinstance(renderer.body, ast.Name) and renderer.body.id == 'export_delivery16'
    assert isinstance(renderer.orelse, ast.Name) and renderer.orelse.id == 'export_edited_16bit'


@pytest.mark.parametrize('blocked,watermark,expected', [
    (False, None, False), (True, None, True), (False, {'alsoClean': True}, True),
])
def test_explicit_native16_retains_existing_shortcut_policy(blocked, watermark, expected):
    guard = compile(ast.Expression(native16_route().test), '<native16-route>', 'eval')
    result = eval(guard, {'__builtins__': {}}, {
        'decision': None, 'watermark': watermark, 'snap_i': {},
        'self': SimpleNamespace(_master16_snapshot_blockers=lambda _: ['edit'] if blocked else []),
    })
    assert bool(result) is expected


@pytest.mark.parametrize('codec,source', [('png', 'png16'), ('tif', 'tiff16')])
def test_neutral_canonical_rgb16_route_preserves_low_bits_without_rgb8(monkeypatch, codec, source):
    import numpy as np
    pytest.importorskip('torch')
    from lumaretouch_engine import export as E
    from lumaretouch_engine.vram import PreviewPipeline
    values = np.arange(64 * 64, dtype=np.uint32).reshape(64, 64)
    pixels = np.stack([(values * k + b) % 65536 for k, b in
                       ((5, 3), (7, 11), (13, 17))], axis=-1).astype(np.uint16)
    decoded = SimpleNamespace(rgb=pixels, raw={'source': source, 'used_preview': False},
        source_icc=None, src_w=64, src_h=64, src_bits=16, fmt=codec, notes=[])
    def forbidden(*_args, **_kwargs):
        pytest.fail('Native16 route used a uint8 framebuffer')
    monkeypatch.setattr(PreviewPipeline, 'pack', forbidden)
    seen = []
    def publish(frame, path, **_options):
        np.testing.assert_array_equal(frame, pixels)
        assert frame.dtype == np.uint16
        assert np.count_nonzero(frame & 255) > 0
        assert min(np.unique(frame[..., c]).size for c in range(3)) > 256
        seen.append(path)
        return {'format': codec, 'bits': 16, 'path': path}
    monkeypatch.setattr(E, '_write_verified_rgb16', publish)
    receipt = E.export_edited_16bit(decoded, E.ExportSpec(strength=0),
        'neutral.' + codec, device='cpu', output_profile='none')
    assert seen == ['neutral.' + codec]
    assert receipt['pipeline'] == 'float32_rgb16'
    assert receipt['source_bits'] == receipt['decoded_bits'] == receipt['bits'] == 16
