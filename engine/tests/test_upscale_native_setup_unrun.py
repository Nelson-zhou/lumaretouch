"""Authored only, NOT RUN. No acceptance/quality claim follows from this file."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest


def test_legacy_rrdb_remains_unavailable_without_touching_model():
    from lumaretouch_engine.upscale_v2.adapter import capability
    with patch('lumaretouch_engine.upscale_v2.adapter.setup_status', side_effect=AssertionError('No legacy admission')):
        result = capability('RealESRGAN_x2plus')
    assert not result.available
    assert 'license' in ';'.join(result.blockers)


def test_fixed_primary_model_profile_has_no_user_pin_escape():
    from lumaretouch_engine.upscale_v2 import setup as S
    assert S.MODEL_ID == 'Swin2SR-classical-sr-x2-64'
    assert S.CHECKPOINT_SHA256 == 'a515955815ab6dba3a9331d8c75db13a5166a5ffbcebf1a95ab676a5656ac4fb'
    assert S.CHECKPOINT_SIZE_BYTES == 48460660
    assert S.CHECKPOINT_LICENSE == 'Apache-2.0'
    with patch.object(S, 'CHECKPOINT_SHA256', None):
        assert 'official_checkpoint_sha256_unestablished' in S.evidence_blockers()
        with patch.object(S, '_lock_model', side_effect=AssertionError('Must block before writes')):
            with pytest.raises(S.ModelInstallError): S.install_model()


def test_result_is_never_identity_fallback_when_unavailable():
    from lumaretouch_engine.upscale_v2 import adapter as A
    from lumaretouch_engine.upscale_v2.source import CanonicalSource
    unavailable = A.BackendCapability('Swin2SR-classical-sr-x2-64', 'contract', False, 'missing', ('missing',), 2)
    source = CanonicalSource(16, 16, b'', hashlib.sha256(b'').hexdigest())
    with patch.object(A, 'capability', return_value=unavailable):
        with pytest.raises(A.BackendUnavailable):
            A.restore_native_candidate(source=source, check_cancelled=lambda: None)


def test_window_plan_covers_native_cores_without_per_tile_phase_reset():
    from lumaretouch_engine.upscale_v2.geometry import plan_native_candidate, iter_native_tiles
    plan = plan_native_candidate(131, 129, model_id='Swin2SR-classical-sr-x2-64', core_size=64, halo=32)
    tiles = list(iter_native_tiles(plan))
    assert sum(tile.core.pixels for tile in tiles) == 131*129
    assert plan.input_alignment == 8
    assert not plan.halo_quality_accepted
    for tile in tiles:
        assert all(value%8 == 0 for value in (tile.model_input.x0, tile.model_input.y0, tile.model_input.x1, tile.model_input.y1))


def test_cli_is_explicit_and_installer_has_no_base_pip_install():
    # Source-wiring guard only, not product execution acceptance.
    setup = Path(__file__).parents[1]/'src/lumaretouch_engine/upscale_v2/setup.py'
    worker = setup.with_name('worker.py').read_text()
    assert 'build_model(torch, checkpoint)' in worker
    assert 'torch.load' not in worker
    assert 'install_offline_policy()' in worker
    assert 'RLIMIT_AS' in worker and 'RLIMIT_CPU' in worker
    assert "'-m', 'pip'" not in setup.read_text()


def test_first_profile_is_one_complete_frame_not_large_photo_proxy():
    from lumaretouch_engine.upscale_v2 import setup as S
    from lumaretouch_engine.upscale_v2.geometry import plan_native_candidate
    assert S.MAX_SIDE == 1024 and S.MAX_PIXELS == 1048576
    for width, height in ((16, 16), (1024, 1024), (1017, 33)):
        plan = plan_native_candidate(width, height, model_id=S.MODEL_ID, core_size=S.CORE_SIZE, halo=S.HALO)
        assert plan.tile_count == 1
        assert plan.padded_width <= 1024 and plan.padded_height <= 1024
    worker = (Path(__file__).parents[1]/'src/lumaretouch_engine/upscale_v2/worker.py').read_text()
    assert 'if plan.tile_count != 1:' in worker
