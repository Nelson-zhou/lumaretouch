"""Source-path regression fixtures, AUTHORED / UNRUN; no product execution performed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def source(name):
    return (ENGINE / name).read_text()


def test_source_fit_is_not_current_proxy():
    text = source('skin_reference_match_inputs.py')
    assert 'capture(engine, expected_source=source' in text
    assert 'capture_original(info[\'path\']' in text
    assert "'skin_reference_match_source_info'" in text
    assert 'pipe.src_f32' not in text


def test_frozen_export_and_preview_have_dedicated_provider():
    assert 'reference_inputs(snapshot,source)' in source('people_engine_runtime.py')
    assert 'reference_inputs(engine,state,support_bank)' in source('people_owned_inputs.py')
    text = source('people_render_runtime.py')
    assert 'captured=skin_reference_match_source' in text
    assert 'prepared.effects+reference_effects' in text
    assert text.index('prepare_reference_match(state') < text.index('if not needed(state,asset_sha256)')


def test_existing_stage_order_preserved_with_independent_prefix():
    text = source('people_effects.py')
    assert "STAGES = ('skin_reference_match', 'skin_reference_body_match', 'body_face_match'" in text
    assert 'skin_reference_match_composition import apply_records_np' in text
    assert "source_effect(self,'skin_reference_match'" in source('vram.py') or '"skin_reference_match"' in source('vram.py')


def test_review_read_does_not_enter_project_recovery_write():
    assert 'skin_reference_match_read_only(msg)' in source('server.py')
    assert 'if skin_reference_read_only(message): return' in source('project_recovery_runtime.py')
    text = source('people_host_commands.py')
    assert "'skin_reference_match_request'" in text
    assert "if reference_action and not result['success']:" in text


def test_saved_support_and_legacy_neutral_contract():
    assert "defaults.pop('lnx.skin_reference_match.v1',None)" in source('people_source_context.py')
    assert 'validate_reference_match(project)' in source('people_host.py')
    assert 'skin_reference_match_relation' in source('people_support_assets.py')
    assert "result['skin_reference_match']=skin_reference_report" in source('people_host.py')


def test_explicit_reviewed_writes_have_independent_history_groups():
    text = source('history_policy.py')
    assert 'in ("skin_reference_match_confirm","skin_reference_match_clear","skin_reference_body_confirm","skin_reference_body_clear")' in text
    assert 'return "people:"+msg["action"]+":"+str(msg.get("request_id"))' in text
