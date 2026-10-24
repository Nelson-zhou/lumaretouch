# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Static route contracts, not execution acceptance."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def method(name):
    text = (ENGINE / 'server.py').read_text()
    node = next(n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


def test_cancel_control_short_circuits_unrelated_ingress_owners():
    source = method('_custom_lut_ingress')
    assert 'if eye_bag_jobs(self).ingress(line): return True' in source
    assert source.index('eye_bag_jobs(self).ingress(line)') < source.index('_primary_calibration_service')


def test_one_event_owner_precedes_reader_start_and_stops_on_eof_and_exit():
    source = method('run')
    assert source.index('eye_bag_jobs(self)') < source.index('reader = threading.Thread')
    assert 'eye_bag_jobs(self).stop()' in source
    assert 'eye_bag_jobs(self).stop()' in method('_custom_lut_reader_stop')


def test_read_callbacks_reach_crop_support_and_complete_render():
    source = (ENGINE / 'eye_bag_preserve_host.py').read_text()
    assert 'cancelled=lambda: JOBS.cancelled(engine)' in source
    assert source.count('cancelled=lambda: JOBS.cancelled(engine)') >= 4
    renderer = (ENGINE / 'portrait_review_render.py').read_text()
    assert 'people_graph=graph, cancelled=cancelled' in renderer
    jobs = (ENGINE / 'eye_bag_review_jobs.py').read_text()
    assert "'eye_bag_confirm'" not in jobs.split('MAX_RECORDS =')[0]
    assert 'release_private(engine)' in jobs


def test_native_control_reuses_writer_and_never_normal_mutation_enqueue():
    native = (ROOT / 'ui/src-tauri/src/engine.rs').read_text()
    assert 'cancel_eye_bag_read' in native and '"eye_bag_cancel"' in native
    api = (ROOT / 'ui/src-tauri/src/people_api.rs').read_text()
    assert 'read_review_binding(id)' in api
    assert 'handle.cancel_eye_bag_read(id)' in api
    assert 'recover_eye_bag_read' in api
