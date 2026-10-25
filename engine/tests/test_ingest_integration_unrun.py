"""Authored UNRUN source-level integration fixtures; no product imports."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / 'engine/src/lumaretouch_engine'
NATIVE = ROOT / 'ui/src-tauri/src'


class IngestionIntegration(unittest.TestCase):
    def test_guard_precedes_recovery_and_history(self):
        source = (ENGINE / 'server.py').read_text()
        dispatch = source[source.index('    def _process_line('):]
        self.assertLess(dispatch.index('ISH.guard_command'), dispatch.index('begin(self, msg, fn)'))
        self.assertLess(dispatch.index("'ingest_session'"), dispatch.index('before = self._history_capture()'))
        self.assertIn('ISH.dispatch_rejected', dispatch)

    def test_internal_precommit_is_not_json_field(self):
        source = (ENGINE / 'managed_import_host.py').read_text()
        self.assertIn('*,trusted_precommit=None,trusted_root=None', source)
        self.assertIn('trusted_precommit(prepared)', source)
        self.assertNotIn("p.get('trusted_precommit')", source)
        self.assertLess(source.index('trusted_root(rootfd)'), source.index('IO.prepare(item'))
        ast.parse(source)

    def test_native_store_requires_validated_receipts(self):
        source = (NATIVE / 'ingest_session_api.rs').read_text()
        self.assertIn('accept_with_context', source)
        self.assertIn('if accepted { crate::project_recovery_fence::observed', source)
        self.assertIn('result["status"] == "readback"', source)
        self.assertIn('{ 240 } else { 256 }', source)
        engine = (NATIVE / 'engine.rs').read_text()
        self.assertIn('v["event"] != "ingest_session_result"', engine)

    def test_owned_epoch_is_checked_at_final_dispatch_lock(self):
        source = (NATIVE / 'native_dispatch.rs').read_text()
        self.assertIn('send_to_engine_at_epoch', source)
        self.assertEqual(source.count('require_dispatch_epoch(handle, expected_epoch)?;'), 2)
        self.assertIn('Some("ingest_session" | "workflow_owner")', source)
        ingest = (NATIVE / 'ingest_session_api.rs').read_text()
        self.assertIn('send_to_engine_at_epoch(request, epoch)', ingest)
        transport = (NATIVE / 'local_workflow_host/transport.rs').read_text()
        self.assertIn('send_to_engine_at_epoch', transport)

    def test_registry_is_actual_engine_catalogue(self):
        source = (ENGINE / 'server.py').read_text()
        self.assertIn('from .command_registry import HANDLED', source)
        tree = ast.parse((ENGINE / 'command_registry.py').read_text())
        catalogue = ast.literal_eval(next(node.value for node in tree.body if isinstance(node, ast.Assign)))
        self.assertIn('ingest_session', catalogue)
        self.assertIn('managed_import', catalogue)
        self.assertIn('export', catalogue)

    def test_shutdown_stops_producers_before_engine(self):
        source = (NATIVE / 'app_shutdown.rs').read_text()
        body = source[source.index('pub(crate) fn shutdown_engine'):]
        self.assertLess(body.index('tether_host::shutdown'), body.index('h.shutdown()'))


class TetherUserWorkflowSource(unittest.TestCase):
    def test_pending_queries_poll_without_replaying_actions(self):
        source = (ROOT / 'ui/src/tetherCapture/controller.ts').read_text()
        self.assertIn('this.receiptTimer = setInterval', source)
        self.assertIn('void this.query(pending.request_id)', source)
        blocker = source[source.index('private commandBlocker'):source.index('async send(command')]
        self.assertLess(blocker.index("command.action === 'stop'"), blocker.index('this.state.pending.length'))

    def test_native_preview_limit_is_visible(self):
        port = (ROOT / 'ui/src/tetherCapture/nativePort.ts').read_text()
        panel = (ROOT / 'ui/src/tetherCapture/TetherCapturePanel.tsx').read_text()
        self.assertIn("supported_preview_modes: ['keep_current']", port)
        self.assertIn('最新照片定位尚未接通', panel)
        self.assertIn('UUID 文件名', panel)
