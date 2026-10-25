# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored UNRUN static integration fixtures; not numerical acceptance."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'


def test_dedicated_source_admission_precedes_capture_session():
    text = (ENGINE / 'lens_blur_host.py').read_text()
    assert 'source_admission(asset,maximum,display_reserve=stage.DISPLAY_RESERVE)' in text
    bounds = (ENGINE / 'lens_blur_admission.py').read_text()
    assert 'pixels*128' in bounds and 'budget.max_candidate_taps' in bounds
    assert 'raise MemoryError' in bounds


def test_one_use_native_and_noncoalesced_read_routes():
    native = (ROOT / 'ui/src-tauri/src/engine.rs').read_text()
    assert native.count('lens_blur_api::blocks_mutation') == 2
    assert native.count('lens_blur_api::read_only') == 2
    assert 'cancel_lens_blur_read' in native
    assert 'lens_blur_api::observe_line' in native


def test_extracted_reader_keeps_separate_job_owners():
    tree = ast.parse((ENGINE / 'read_job_ingress.py').read_text())
    assert any(isinstance(node, ast.FunctionDef) for node in tree.body)
    text = (ENGINE / 'read_job_ingress.py').read_text()
    assert 'lens_blur_jobs' in text
    assert 'expression_replacement_jobs' in text


def test_ui_owner_not_panel_lifetime():
    app = (ROOT / 'ui/src/App.tsx').read_text()
    assert 'useLensBlur(' in app and '<LensWorkspaceHost' in app
    text = (ROOT / 'ui/src/lensBlur/useLensBlur.ts').read_text()
    assert 'queueBusy is admission-only' in text
    assert 'current_scope' in text and 'requestReconciliation' in text


def test_outer_guard_rejection_uses_exact_write_envelope():
    tree = ast.parse((ENGINE / 'lens_blur_host.py').read_text())
    handler = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'dispatch_rejected')
    source = ast.unparse(handler)
    assert "result.pop('message', None)" in source
    assert "result.update(status='ready', receipt=receipt)" in source


def test_creative_admission_does_not_remove_body_workspace_guard():
    text = (ROOT / 'ui/src/App.tsx').read_text()
    body = text.split('const bodyToolsBlocked=', 1)[1].split('const legs=', 1)[0]
    image = text.split('const imageToolBusy=', 1)[1].split('const hairToolBusy=', 1)[0]
    assert "workspace!=='retouch'" in body
    assert "workspace!=='retouch'" not in image
    assert "const hairToolBusy=imageToolBusy||workspace!=='retouch'" in text


def test_reader_hash_excludes_dispatcher_transport_counter():
    text = (ENGINE / 'lens_blur_jobs.py').read_text()
    ingress = text.split('def ingress(self, line):', 1)[1].split('def stop(self):', 1)[0]
    assert "request.pop('_host_request_id', None)" in ingress
    assert ingress.index("request.pop('_host_request_id', None)") < ingress.index("self.register(request.get('request_id'), command_hash(request))")
