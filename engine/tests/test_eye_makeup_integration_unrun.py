# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored integration regressions. UNRUN; never imported during source review."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def source(name):
    return (ENGINE / (name + '.py')).read_text()


def test_actual_source_and_atomic_bilateral_validation():
    runtime = source('people_render_runtime')
    assert "prepare_eye_makeup_enhance(entry['face_ref'],analysis,source," in runtime
    assert 'eye_makeup_enhance_assets' in source('people_engine_runtime')
    assert 'validate_leaf(path, patch[\'value\'])' in source('people_edit')
    assert 'return validate_leaf(path, value)' in source('creative_derived_makeup')
    assert "'eye_makeup_enhance_protocol': 1" in source('eye_makeup_enhance_state')


def test_integer_source_centres_on_every_render_grid():
    tree = ast.parse(source('eye_makeup_enhance_layer'))
    observe = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_observe')
    coordinates = [n for n in observe.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id in ('xx', 'yy') for t in n.targets)]
    assert len(coordinates) == 2
    for assignment in coordinates:
        assert not any(isinstance(n, ast.Constant) and n.value == .5 for n in ast.walk(assignment))
    assert 'W-1' in source('eye_makeup_enhance_layer')
    assert 'H-1' in source('eye_makeup_enhance_layer')


def test_release_finishes_without_mutation_even_if_refresh_fails():
    workflow = (ROOT / 'ui/src/people/workflow.ts').read_text()
    assert '(faceStyleRead || decorationReleased || sculptReleased || eyeMakeupReleased)' in workflow
    assert 'eyeMakeupEnhanceReleasedRequestId: eyeMakeupReleased ? command.request_id : null' in workflow
    assert "catch {refreshError = decorationReleased || sculptReleased || eyeMakeupReleased" in workflow
    for name in ('engine', 'native_dispatch', 'project_recovery_fence', 'preset_alias_recovery_fence'):
        assert 'eye_makeup_enhance::read_only' in (ROOT / 'ui/src-tauri/src' / (name + '.rs')).read_text()


def test_packaging_and_shared_composition_are_explicit():
    assert 'eye_makeup_enhance_composition import apply_np' in source('people_effects')
    assert 'eye_makeup_enhance_composition import apply_t' in source('people_pipeline')
    assert "source_effect(self,'eye_makeup_enhance',out)" in source('vram')
    package = (ROOT / 'packaging/stage-engine.sh').read_text()
    assert 'eye_makeup_enhance/THIRD_PARTY.md' in package
    assert 'liblrt_eye_makeup_enhance.so' in package


def test_historical_context_and_exact_dormant_link_policy(monkeypatch):
    from copy import deepcopy
    from lumaretouch_engine import people_state as P, people_algorithms as A
    from lumaretouch_engine import people_source_context as C
    from lumaretouch_engine.eye_makeup_enhance_state import OP
    state = P.empty()
    original = A.defaults()
    old = deepcopy(original)
    old.pop(OP)
    monkeypatch.setattr(A, 'defaults', lambda: deepcopy(old))
    before = C.digest(state, 'a'*64)
    monkeypatch.setattr(A, 'defaults', lambda: deepcopy(original))
    assert C.digest(state, 'a'*64) == before
    edited = P.set_override(state, 'all_people', 'a'*64, OP, '/amount/left', 0.0)
    assert C.digest(edited, 'a'*64) != before
    plan = source('people_render_plan')
    assert "('/amount/linked','/saturation/linked','/brightness/linked','/structure/linked')" in plan
    assert "type(record['value']) is bool" in plan


def test_original_rgb_decode_rejects_coverage_before_conversion():
    tree = ast.parse(source('decode'))
    for name in ('_load_rgb_pillow', '_load_full_pillow'):
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        calls = sorted((n.lineno, n.func.id) for n in ast.walk(node)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                       and n.func.id in ('require_opaque_8bit', '_to_working_srgb'))
        assert [name for _, name in calls] == ['require_opaque_8bit', '_to_working_srgb']
    # Creative RGBA assets retain their separate alpha-capable conversion route.
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_to_working_srgb')
    assert 'require_opaque_8bit' not in ast.unparse(function)
