"""AUTHORED / UNRUN source-route specifications, not runtime acceptance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'lumaretouch_engine'


def test_main_frame_routes_prepare_geometry_then_id_then_recovery():
    lines = [line for line in (ROOT / 'server.py').read_text().splitlines()
             if 'IDR.sync(' in line and 'ERR.sync(' in line and 'self._people_sync(' in line]
    assert len(lines) == 4
    assert all(line.index('self._people_sync(') < line.index('IDR.sync(') < line.index('ERR.sync(')
               for line in lines)


def test_id_recovery_is_around_its_own_stage_not_legacy_background():
    source = (ROOT / 'vram.py').read_text()
    assert "self.effect_recovery.apply('id_background', out," in source
    assert 'self.id_background.apply(out,self.align_source_grade_mask)' in source
    assert "self.effect_recovery.apply('background_replace', t, out," in source


def test_original_project_and_final_export_keep_id_recovery_proofs():
    project = (ROOT / 'id_background_project.py').read_text()
    runtime = (ROOT / 'id_background_runtime.py').read_text()
    assert 'from .id_background_recovery import validate_state' in project
    assert 'from .id_background_recovery import verify_export' in runtime
    assert 'spec._id_recovery_consumer=None' in runtime
