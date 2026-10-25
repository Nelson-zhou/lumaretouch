# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Static wiring and real raster parity cases, not acceptance."""
import ast
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def stroke(ident='one', mode='clear', feather=.5, points=None):
    return {'id': ident, 'mode': mode, 'amount': .75, 'flow': .6, 'feather': feather,
            'radius': .2, 'points': points or [{'x': .2, 'y': .3}, {'x': .8, 'y': .7}]}


@pytest.mark.parametrize('strokes', [[], [stroke()], [stroke(feather=0)],
    [stroke(), stroke('two', 'blur', .25)], [stroke(points=[{'x': 0., 'y': 1.}])]])
def test_stroke_local_raster_matches_original_capsule_math(strokes):
    from lumaretouch_engine import lens_blur_refinement as original
    from lumaretouch_engine import lens_cohort_refinement as bounded
    args = dict(max_bytes=32*1024*1024, max_pixels_examined=64_000_000)
    assert bounded.rasterize(strokes, 31, 23, **args) == original.rasterize(strokes, 31, 23, **args)


def test_refinement_cancellation_never_returns_partial_raster():
    from lumaretouch_engine import lens_cohort_refinement as bounded
    with pytest.raises(InterruptedError):
        bounded.rasterize([stroke()], 31, 23, max_bytes=32*1024*1024,
                          max_pixels_examined=64_000_000, cancelled=lambda: True)


def test_versioned_source_import_is_opt_in_and_neutral_only():
    text = (ENGINE / 'creative_document_base.py').read_text()
    tree = ast.parse(text)
    capture = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'capture_current_asset')
    assert 'neutral_import_version=0' in ast.unparse(capture)
    assert 'neutral_import_version == 1 and neutral' in text
    assert 'creative_document_import_bounded import import_file as importer' in text
    assert 'max(pixels, ow * oh) * 96' in text  # Arbitrary edits are not silently admitted.


def test_wire_three_and_both_recipe_math_paths_are_explicit():
    stage = (ENGINE / 'lens_blur_stage.py').read_text()
    host = (ENGINE / 'lens_blur_host.py').read_text()
    native = (ROOT / 'ui/src-tauri/src/lens_blur_protocol.rs').read_text()
    assert 'WIRE_PROTOCOL = 3' in stage and 'PROTOCOL = 3' in host
    assert 'const PROTOCOL: u64 = 3' in native
    for text in (stage, native):
        assert 'lnx.lens_blur.cohort.v2' in text and 'cohort-fft-f64-v2-00020001' in text
    assert "if command['recipe']['version'] == 2:" in stage
    assert 'return prepare_validated' in stage


def test_full_grid_depth_is_not_allocated_by_cohort_stage():
    text = (ENGINE / 'lens_blur_cohort_stage.py').read_text()
    assert '_full_depth(' not in text and 'np.empty' not in text
    assert 'native.render(source.content' in text
    assert 'manual_depth_acknowledged=True' in text
    assert 'max_live_bytes=budget.max_bytes-retained_other-reserve' in text
    assert 'S.Candidate' in text and "asset['id'][7:]" in text


def test_native_job_is_packaged_separately_from_legacy():
    text = (ROOT / 'packaging/stage-engine.sh').read_text()
    assert 'liblrt_lens_aperture.so' in text and 'liblrt_lens_cohort.so' in text


def test_acquisition_keeps_small_direct_path_when_cohort_reservation_does_not_fit():
    from types import SimpleNamespace
    from lumaretouch_engine.lens_blur_admission import source_admission
    asset = {'width': 2, 'height': 2, 'content': b'\0'*64, 'original': b'', 'icc': b''}
    budget = SimpleNamespace(max_bytes=300*1024*1024, max_candidate_taps=250_000_000)
    source_admission(asset, budget, display_reserve=96*1024*1024,
                     renderers=('direct-v1', 'cohort-fft-v2'))
    with pytest.raises(MemoryError):
        source_admission(asset, budget, display_reserve=96*1024*1024,
                         renderers=('cohort-fft-v2',))


def test_native_negotiation_and_session_cancel_do_not_depend_on_expired_image():
    native = (ROOT / 'ui/src-tauri/src/lens_blur_api.rs').read_text()
    assert 'self.capability["renderers"].as_array()' in native
    workflow = (ROOT / 'ui/src/lensBlur/workflow.ts').read_text()
    cancel = workflow.split('async function cancel()', 1)[1].split('async function check()', 1)[0]
    assert 'token: null' in cancel and 'state.review?.token' not in cancel
    assert 'unresolved()' in cancel  # Never treat an entered unknown Apply as cancellable.


def test_legacy_import_retry_is_explicit_post_validation_and_outside_exception_scope():
    tree = ast.parse((ENGINE / 'creative_document_base.py').read_text())
    capture = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'capture_current_asset')
    exceptions = [n for n in ast.walk(capture) if isinstance(n, ast.ExceptHandler)
                  and isinstance(n.type, ast.Name) and n.type.id == 'ImportBudgetExceeded']
    assert len(exceptions) == 1
    handler = ast.unparse(exceptions[0])
    assert 'allow_legacy_import_budget_fallback' in handler
    assert 'error.__traceback__ = None' in handler
    assert 'identity = import_file' not in handler
