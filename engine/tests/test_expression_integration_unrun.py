"""Authored static integration fixtures. UNRUN; imports no product modules."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[2]

def source(path):return (ROOT/path).read_text()

def test_expression_registration_and_caps():
    server=source('engine/src/lumaretouch_engine/server.py')
    assert 'def cmd_expression_replacement' in server
    assert 'expression_rejected(self,msg,dispatch_error' in server
    assert len(server.splitlines())<=7065
    assert len(source('ui/src/App.tsx').splitlines())<=2160
    assert len(source('ui/src-tauri/src/main.rs').splitlines())<=2060

def test_copy_family_not_second_root_with_same_source():
    host=source('engine/src/lumaretouch_engine/creative_document_host.py')
    assert "row['root_document_id'] = source['root_document_id']" in host
    assert "row['copy_number'] = 1 + max" in host
    assert "row[VP.KEY] = {'version':1,'people_graph':PS.empty()" in host

def test_actual_analysis_and_no_double_fusion():
    capture=source('engine/src/lumaretouch_engine/expression_replacement_source.py')
    assert 'capture_current_asset' in capture and "F.build('mediapipe')" in capture
    stage=source('engine/src/lumaretouch_engine/expression_replacement_stage.py')
    assert 'CreativeRenderer' in stage and 'asset_image(rendered' in stage
    assert 'candidate_sha256' in stage

def test_native_exact_receipts_and_epoch_retirement():
    host=source('ui/src-tauri/src/expression_replacement_api.rs')
    assert 'wire::apply_matches' in host and 'retired_read' in host
    assert 'r.request.action != "apply"' in host
    engine=source('ui/src-tauri/src/engine.rs')
    assert 'observe_line(inspection_epoch, &line)' in engine
    assert 'cancel_expression_replacement' in engine

def test_ui_revision_domains_and_owned_queue_are_separate():
    hook=source('ui/src/expressionReplacement/useExpressionReplacement.ts')
    assert 'binding.document_revision!==this.context.hostRevision' not in hook
    assert '!this.context.queueBusy' in hook
    controller=source('ui/src/expressionReplacement/controller.ts')
    assert "donor:null,donor_ref:null,donor_displayed:false,phase:'choosing'" in controller

def test_python_sources_parse_without_product_import():
    for path in (ROOT/'engine/src/lumaretouch_engine').glob('expression_replacement_*.py'):
        ast.parse(path.read_text())
