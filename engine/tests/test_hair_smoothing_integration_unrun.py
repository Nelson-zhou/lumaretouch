# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source-contract checks; not runtime/photo acceptance."""
from pathlib import Path
import ast
import json

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def test_only_exact_requested_leaf_has_a_reachable_panel():
    text = (ROOT / 'ui/src/components/RetouchPanel.tsx').read_text()
    assert "leaf.path==='头发柔顺'&&props.hairSmoothingPanel" in text
    assert "leaf.path==='头发柔顺/发丝调整'&&props.hairSmoothingPanel" not in text
    spec = json.loads((ROOT / 'ui/src/spec/refine.json').read_text())
    assert '头发柔顺/发丝调整' in json.dumps(spec, ensure_ascii=False)


def test_source_stage_order_and_exact_eligibility_retention():
    tree = ast.parse((ENGINE / 'people_effects.py').read_text())
    stages = next(ast.literal_eval(row.value) for row in tree.body
                  if isinstance(row, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STAGES' for t in row.targets))
    assert stages.index('hair_unification') < stages.index('hair_smoothing') < stages.index('eye_light')
    assert 'eligibility: object = None' in (ENGINE / 'people_effects.py').read_text()
    assert "defaults.pop('lnx.hair_smoothing.v1',None)" in (ENGINE / 'people_source_context.py').read_text()


def test_shared_pipeline_never_silently_omits_the_operation():
    for name in ('people_render_runtime.py', 'people_engine_runtime.py', 'people_owned_inputs.py',
                 'people_export.py', 'full_candidate_render.py', 'people_host_commands.py'):
        assert 'hair_smoothing' in (ENGINE / name).read_text()
    assert 'hair_smoothing_source_info' in (ENGINE / 'hair_smoothing_inputs.py').read_text()
    assert '_hair_smoothing_repair_inputs' in (ENGINE / 'export_recipe.py').read_text()
    assert 'hair_smoothing_measurements' in (ENGINE / 'full_candidate_render.py').read_text()


def test_packaging_stages_actual_independent_core_without_runtime_compile():
    text = (ROOT / 'packaging/stage-engine.sh').read_text()
    assert 'liblrt_hair_smoothing.so' in text and 'third_party/hair_smoothing' in text
    native = (ENGINE / 'hair_smoothing_native.py').read_text()
    assert 'subprocess' not in native and 'rustc' not in native and 'pip install' not in native


def test_unknown_publication_has_no_create_or_timeout_unlock():
    fence = (ROOT / 'ui/src-tauri/src/project_recovery_fence.rs').read_text()
    assert 'crate::people_api::hair_smoothing::mutation(&request.command)' in fence
    assert 'let query_or_reopen' in fence and '!replaced // A new empty project keeps the old live document recipes.' in fence
    receipt = (ROOT / 'ui/src-tauri/src/receipt_host.rs').read_text()
    assert 'smoothing_read_reconciliation' in receipt
    assert 'bound_hair_smoothing' in receipt and 'failed_bound_hair_smoothing' in receipt
    assert 'HAIR_SMOOTHING_RESULT_BYTES: usize = 18 * 1024 * 1024' in receipt
    api = (ROOT / 'ui/src-tauri/src/people_api.rs').read_text()
    assert 'reject_malformed_hair_smoothing' in api and 'unique_json(raw,18*1024*1024)' in api
