"""Authored source-boundary fixtures only; UNRUN, no product imports performed."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def text(name):
    return (ENGINE / name).read_text()


def test_independent_body_intent_preserves_old_face_default_digest():
    assert "OP = 'lnx.skin_reference_body_match.v1'" in text('skin_reference_body_state.py')
    assert "defaults.pop('lnx.skin_reference_body_match.v1',None)" in text('people_source_context.py')
    assert 'SKIN_REFERENCE_BODY.neutral()' in text('people_algorithms.py')


def test_joint_fullsource_preparation_before_common_geometry():
    source = text('people_render_runtime.py')
    assert 'or body_reference_requests(state,asset_sha256)' in source
    assert 'face_records=reference_effects' in source
    assert 'common_reference(state,skin_reference_match_assets or {},asset_sha256,body_bank,analyses)' in source
    assert 'prepared.effects+reference_effects+body_reference_effects' in source
    stage = text('vram.py')
    assert stage.index("'skin_reference_match',out") < stage.index("'skin_reference_body_match',out") < stage.index("'body_face_match',out")


def test_body_only_source_capture_and_symmetric_foreign_reservation():
    assert 'or body_refs(state, asset)' in text('skin_reference_match_inputs.py')
    assert 'reference_body_attached(state, assets, ref)' in text('skin_colour_body_support.py')
    assert "'skin_reference_match_body_visibility'" in text('people_support_assets.py')


def test_dedicated_protocol_uses_existing_command_owner():
    assert 'skin_reference_body_host as BODY' in text('people_reference_dispatch.py')
    assert 'reference_module(action)' in text('people_host_commands.py')
    assert "'skin_reference_body_request'" in text('people_host_commands.py')
    assert '"skin_reference_body_confirm","skin_reference_body_clear"' in text('history_policy.py')


def test_preserved_generic_transfer_and_owned_history_guards():
    assert 'require_body_reference_transition(target_state,out)' in text('people_transfer_adapter.py')
    assert 'validate_reference_body(project)' in text('people_host.py')
    assert 'require_body_reference_transition(self,before,candidate)' in text('people_host.py')


def test_dedicated_support_and_capture_overlap_are_not_generic_fallbacks():
    source = text('people_render_runtime.py')
    assert "'skin_reference_match_body_visibility'" in source
    assert 'capture_budget=max(0,remaining-reference_analysis_bytes(analyses))' in source
    assert 'skin_reference_match_source(byte_budget=capture_budget' in source
