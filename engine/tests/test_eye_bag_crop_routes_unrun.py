# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source-only route and ownership regression contracts."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def test_source_page_is_explicit_read_and_does_not_publish():
    text = (ENGINE / 'people_host_commands.py').read_text()
    tree = ast.parse(text)
    value = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'EYE_BAG_READS' for t in n.targets))
    assert 'eye_bag_source_image' in ast.literal_eval(value.args[0])
    assert "'eye_bag_source_image':eye_bag_review.source_image" in text
    assert "eye_bag_crop_remaining=2" in text
    assert "body.get('kind')=='eye_bag_source_image'" in text
    host = (ENGINE / 'eye_bag_preserve_host.py').read_text()
    function = next(n for n in ast.parse(host).body if isinstance(n, ast.FunctionDef) and n.name == 'source_image')
    source = ast.get_source_segment(host, function)
    assert '_reference(' in source
    assert '_publish' not in source and 'set_override' not in source


def test_original_and_derived_share_paged_route_without_owner_bypass():
    derived = (ENGINE / 'creative_derived_effects.py').read_text()
    assert "'eye_bag_source_image', 'eye_bag_reference'" in derived
    assert 'check_action(action,payload,target)' in derived
    native = (ROOT / 'ui/src-tauri/src/people_api.rs').read_text()
    assert '"eye_bag_source_image"' in native
    ui = (ROOT / 'ui/src/people/model.ts').read_text()
    assert "'eye_bag_source_image'" in ui
    recovery = (ENGINE / 'project_recovery_runtime.py').read_text()
    assert 'eye_bag_read_only(message)' in recovery


def test_new_crop_source_does_not_replace_original_solver_or_mask_owner():
    source = (ENGINE / 'eye_bag_preserve_crop.py').read_text()
    assert 'from .spill_removal_paint_source import source_pixels' in source
    assert 'replay_repair_t' in source
    assert 'people_support_assets' not in source
    assert '.resize(' not in source and '.thumbnail(' not in source
    assert 'MAX_SOURCE_PIXELS = 32_000_000' in source
    assert 'MAX_CROP_PIXELS = 4_000_000' in source
