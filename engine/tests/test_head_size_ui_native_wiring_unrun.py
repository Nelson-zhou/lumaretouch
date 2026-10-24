# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Static cross-layer contracts, not compiler/UI acceptance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text()


def test_actual_body_workspace_exposes_independent_complete_head_control():
    app = source('ui/src/App.tsx')
    tools = source('ui/src/legShape/BodyShapeTools.tsx')
    assert 'const headSize=useHeadSizeWorkflow' in app
    assert 'headSize={headSize}' in app
    assert 'pending:headSize.busy' in app
    assert 'check:headSize.check' in app
    assert '[data-head-size-workflow]' in app
    assert 'data-requirement-id="LNX-REF-PC-32473-C-dc1b0ba40a"' in tools
    assert 'data-tool-anchor="小头"' in tools
    assert '<HeadSizeWorkspace owner={headSize}' in tools
    assert '"小头"' in source('ui/src/toolRouting/coverage.ts')


def test_native_command_types_and_handler_are_real_not_waist_alias():
    native = source('ui/src/native.ts')
    assert 'head_size?: import(\'./headSize/model\').HeadSizeView' in native
    assert 'export function runHeadSize' in native
    assert "tauriInvoke<import('./headSize/nativeTransport').Mailbox>('head_size'" in native
    main = source('ui/src-tauri/src/main.rs')
    assert 'mod head_size_api;' in main
    assert 'head_size_api::head_size' in main


def test_native_query_lifecycle_and_validated_publication_are_wired():
    engine = source('ui/src-tauri/src/engine.rs')
    dispatch = source('ui/src-tauri/src/native_dispatch.rs')
    assert 'crate::head_size_api::read_only(&cmd)' in engine
    assert 'v["event"] != "head_size_result"' in engine
    assert '"head_size_result" => { if crate::head_size_api::receive' in engine
    assert 'crate::head_size_api::ready(inspection_epoch, v["head_size_protocol"]' in engine
    assert 'crate::head_size_api::ended(inspection_epoch)' in engine
    assert 'crate::head_size_api::reset(epoch)' in source('ui/src-tauri/src/capture_lifecycle.rs')
    assert 'if crate::head_size_api::read_only(&cmd)' in dispatch
    assert '(name != "head_size" || cmd["action"] == "edit")' in dispatch
    assert '"head_size" => crate::head_size_api::enqueue' in dispatch


def test_no_unreviewed_head_scalar_batch_or_preset_option():
    assert 'lnx.head_size.v1' not in source('ui/src/batch/batchScopeOptions.ts')
    assert 'lnx.head_size.v1' not in source('ui/src/presets/presetModel.ts')
