"""AUTHORED / UNRUN: shadow precision, source ownership and prepared proofs.

Native estimation is mocked where stated. These fixtures do not establish
photographic quality, native correctness, performance or successful execution.
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest

from lumaretouch_engine import id_background_state as I
from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import id_background_runtime as R
from lumaretouch_engine import original_shadow_state as S
from lumaretouch_engine import original_shadow_render as O
from lumaretouch_engine import original_shadow_native as N
from lumaretouch_engine import local_mask_state as M


def binding(ident, shape=(2, 4)):
    h, w = shape
    mask = M.empty(); mask['source'] = {'sha256': 'a' * 64, 'width': w, 'height': h}
    mask['recipe']['objects'] = [{'id': ident, 'name': ident, 'enabled': True,
        'operation': 'add', 'kind': 'radial', 'opacity': 1., 'feather': 0.,
        'center': [.5, .5], 'axes': [[.2, 0.], [0., .2]]}]
    return S.check_binding({'version': 1, 'reviewed': True, 'mask': mask,
                            'recipe_sha256': S.digest(mask)})


def recipe(shape=(2, 4), *, enabled=True, strength=50):
    subject = binding('subject', shape)
    value = I.empty(); value.update(enabled=True, source=subject['mask']['source'])
    value['support']['subject'] = U.check_binding({**subject, 'category': 'subject'}, 'subject')
    return I.with_original_shadow(value, {**S.neutral(), 'enabled': enabled, 'strength': strength,
        'uniform_floor_confirmed': True, 'lit_floor': binding('lit', shape),
        'retention': binding('retained', shape)})


def mocked_fields(shape=(2, 4)):
    value = recipe(shape)
    pixels = np.full((*shape, 3), 32768, np.uint16)
    alpha = np.zeros(shape, np.float32)
    bg = np.full((*shape, 3), .8, np.float32)
    with patch.object(S, 'raster', return_value=np.ones(shape, np.float32)), \
         patch.object(N, 'prepare', return_value=np.full(shape, .4, np.float32)), \
         patch.object(N, 'apply', side_effect=lambda background, shadow, **kw:
                      (background * (1 - shadow[..., None] * kw['strength'])).astype(np.float32)):
        output, proof = O.prepare(value, pixels, alpha, bg)
    fields = {'alpha': alpha, 'background': output, 'encoding': N.ENCODING,
              'render_scale': 1., 'original_shadow_source': proof}
    return value, pixels, fields


def test_native_precision_decoding_never_uses_rgb8():
    pixels = np.array([[[256, 257, 258], [32767, 32768, 32769]]], np.uint16)
    out = O.linear_source(pixels)
    x = pixels.astype(np.float32) / 65535.
    expected = np.where(x <= .04045, x / 12.92, ((x + .055) / 1.055) ** 2.4)
    assert np.array_equal(out, expected)
    assert len(set(out[0, 0])) == 3 and not out.flags.writeable
    floats = x + np.float32(.000001)
    assert not np.array_equal(O.linear_source(floats), out)


def test_proxy_rgba_hdr_and_float64_source_refuse_without_clipping():
    source = recipe()['source']
    for pixels in (np.ones((1, 2, 3), np.float32), np.ones((2, 4, 4), np.float32),
                   np.full((2, 4, 3), 1.01, np.float32), np.full((2, 4, 3), np.nan, np.float32),
                   np.ones((2, 4, 3), np.float64)):
        with pytest.raises(ValueError): O.source_identity(pixels, source)
    with pytest.raises(ValueError):
        O.source_identity(np.ones((2, 4, 3), np.float32), source, full_source=False)


def test_disabled_or_zero_strength_never_invoke_native_or_change_background():
    bg = np.full((2, 4, 3), .42, np.float32)
    for value in (recipe(enabled=False), recipe(strength=0)):
        with patch.object(N, 'prepare', side_effect=AssertionError('No estimator')):
            result, proof = O.prepare(value, None, None, bg)
        assert result is bg and proof is None


def test_review_roles_are_distinct_source_bound_vectors():
    value = recipe()
    original = deepcopy(value)
    assert I.check(value) == original
    value['original_shadow']['retention'] = deepcopy(value['original_shadow']['lit_floor'])
    with pytest.raises(ValueError): I.check(value)
    value = recipe(); value['original_shadow']['uniform_floor_confirmed'] = False
    with pytest.raises(ValueError): I.check(value)
    value = recipe(); value['selected_support'] = 'all'
    with pytest.raises(ValueError): I.check(value)
    value = recipe(); value['shadow']['kind'] = 'hard'
    with pytest.raises(ValueError): I.check(value)
    value['original_shadow']['strength'] = 0
    assert I.check(value)['shadow']['kind'] == 'hard'


def test_strength_only_enters_background_application_and_subject_is_unchanged():
    value = recipe(strength=37)
    pixels = np.full((2, 4, 3), 32768, np.uint16)
    alpha = np.full((2, 4), .3, np.float32); before = alpha.copy()
    bg = np.full((2, 4, 3), .8, np.float32)
    with patch.object(S, 'raster', return_value=np.ones((2, 4), np.float32)), \
         patch.object(N, 'prepare', return_value=np.zeros((2, 4), np.float32)) as estimator, \
         patch.object(N, 'apply', return_value=bg.copy()) as application:
        _, proof = O.prepare(value, pixels, alpha, bg)
    assert 'strength' not in estimator.call_args.kwargs
    assert application.call_args.kwargs['strength'] == .37
    assert np.array_equal(alpha, before)
    assert proof['reviewed_alpha_sha256'] == O._hash(alpha)
    assert proof['recipe_sha256'] == O.recipe_digest(value)


def test_source_mutation_during_native_preparation_refuses_publication():
    value = recipe(); pixels = np.full((2, 4, 3), 32768, np.uint16)
    alpha = np.zeros((2, 4), np.float32); bg = np.full((2, 4, 3), .8, np.float32)
    def mutate(*args, **kwargs):
        pixels[0, 0, 0] += 1
        return np.zeros((2, 4), np.float32)
    with patch.object(S, 'raster', return_value=np.ones((2, 4), np.float32)), \
         patch.object(N, 'prepare', side_effect=mutate), patch.object(N, 'apply', return_value=bg.copy()):
        with pytest.raises(ValueError): O.prepare(value, pixels, alpha, bg)


def test_full_prepared_proof_binds_source_background_and_whole_recipe():
    value, pixels, fields = mocked_fields()
    spec = SimpleNamespace(id_background=value, _original_shadow_source_input=pixels)
    original = R._prepared_proof(spec, fields)
    assert original == R._prepared_proof(spec, fields)
    for key in ('source', 'background', 'recipe'):
        changed = deepcopy(fields); source = pixels.copy(); spec.id_background = deepcopy(value)
        if key == 'source': source[0, 0, 0] += 1
        if key == 'background': changed['background'][0, 0, 0] += .001
        if key == 'recipe': spec.id_background['original_shadow']['strength'] += 1
        spec._original_shadow_source_input = source
        with pytest.raises(ValueError): R._prepared_proof(spec, changed)


def test_only_completed_background_is_reduced_for_display_never_upsampled():
    scalar = np.array([[0., .2, .4, .6], [.2, .4, .6, .8]], np.float32)
    rgb = np.repeat(scalar[..., None], 3, axis=2)
    reduced = O._display_background(rgb, (1, 2), lambda: False)
    assert reduced.dtype == np.float32 and reduced.shape == (1, 2, 3)
    assert not reduced.flags.writeable
    with pytest.raises(ValueError): O._display_background(reduced, (2, 4), lambda: False)


def test_background_application_precedes_any_display_reduction():
    value = recipe(); pixels = np.full((2, 4, 3), 32768, np.uint16)
    alpha = np.zeros((2, 4), np.float32)
    opacity = np.array([[0., 1., 0., 1.], [0., 1., 0., 1.]], np.float32)
    bg = np.repeat(np.array([[.2, .8, .2, .8], [.2, .8, .2, .8]], np.float32)[..., None], 3, axis=2)
    completed = bg * (1 - opacity[..., None] * .5)
    with patch.object(S, 'raster', return_value=np.ones((2, 4), np.float32)), \
         patch.object(N, 'prepare', return_value=opacity), \
         patch.object(N, 'apply', return_value=completed) as application:
        out, proof = O.prepare(value, pixels, alpha, bg, render_shape=(1, 2))
    assert application.call_args.args[0].shape == (2, 4, 3)
    assert application.call_args.args[1].shape == (2, 4)
    assert np.array_equal(out, O._display_background(completed, (1, 2), lambda: False))
    assert proof['shape'] == [2, 4, 3] and proof['render_shape'] == [1, 2, 3]
    assert proof['full_background_sha256'] == O._hash(completed)
    assert proof['background_sha256'] == O._hash(out)


def test_nonuniform_asset_display_is_exactly_neutral_and_continuous_at_zero():
    full = np.repeat(np.array([[.2, .8, .3, .9], [.2, .8, .3, .9]], np.float32)[..., None], 3, axis=2)
    display = np.array([[[.13, .27, .41], [.72, .54, .38]]], np.float32)
    neutral, base_hash, shade_hash = O._display_transmission(full, full.copy(), display, lambda: False)
    assert np.array_equal(neutral, display)
    assert base_hash == shade_hash
    tiny = full * np.float32(1 - 0.000001)
    actual, _, _ = O._display_transmission(full, tiny, display, lambda: False)
    assert np.all(actual <= display)
    assert np.max(np.abs(actual - display)) < .000002
    assert not np.allclose(actual, O._display_background(tiny, (1, 2), lambda: False))
    with pytest.raises(ValueError):
        O._display_transmission(full, full * 1.01, display, lambda: False)


def test_png16_gray_and_opaque_alpha_metadata_reach_genuine_decoder():
    class ImageContext:
        width, height, mode, format = 4, 2, 'I', 'PNG'
        info = {'transparency': 65535, 'cicp': (1, 13, 0, 1)}
        def getbands(self): return ('I',)
        def __enter__(self): return self
        def __exit__(self, *_): return False
    with patch('lumaretouch_engine.decode.is_raw', return_value=False), \
         patch('lumaretouch_engine.full_source_working.source_bits', return_value=16), \
         patch('lumaretouch_engine.full_source_working.require_opaque_8bit', side_effect=AssertionError('No RGB8 inspection')), \
         patch('PIL.Image.open', return_value=ImageContext()):
        assert O.verify_original_format('/review/native16.png') == 16


def test_native_budget_and_status_errors_never_publish_partial_output():
    with pytest.raises(ValueError): N.memory_estimate((65537, 1))
    with pytest.raises(ValueError): N.memory_estimate((1, 32_000_001))
    for code in (1, 2, 5, 6, 7):
        with pytest.raises(ValueError): N._result(code, lambda: False, [])
    with pytest.raises(InterruptedError): N._result(3, lambda: False, [])
    with pytest.raises(MemoryError): N._result(4, lambda: False, [])
