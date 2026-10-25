# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN source-wiring fixtures. Not execution/quality acceptance."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PortraitCropIntegration(unittest.TestCase):
    def text(self, path):
        return (ROOT / path).read_text()

    def test_dedicated_history_and_raw_cancel_registration(self):
        server = self.text('engine/src/lumaretouch_engine/server.py')
        self.assertIn('class Engine(PortraitCropEngineMixin,', server)
        self.assertIn("('portrait_crop', 'lens_blur'", server)
        self.assertIn('"portrait_crop": self._portrait_crop_capability()', server)
        registry = self.text('engine/src/lumaretouch_engine/command_registry.py')
        self.assertIn('HANDLED = ("portrait_crop",', registry)
        ingress = self.text('engine/src/lumaretouch_engine/read_job_ingress.py')
        self.assertIn('if crop_jobs(engine).ingress(line): return True', ingress)
        self.assertIn('crop_jobs(engine).stop()', ingress)

    def test_packaged_real_core_and_unchanged_legacy_entry(self):
        stage = self.text('packaging/stage-engine.sh')
        self.assertIn('core/portrait_crop/build_portrait_crop.sh', stage)
        self.assertIn('liblrt_portrait_crop.so', stage)
        app = self.text('ui/src/App.tsx')
        self.assertIn('<PortraitCropWorkspaceHost ', app)
        self.assertIn('<CropModal open={cropOpen}', app)
        self.assertIn('portraitCrop:portraitCropBusy', app)

    def test_native_owned_dispatch_and_receipts(self):
        native = self.text('ui/src-tauri/src/engine.rs')
        for hook in ('blocks_mutation', 'read_only', 'observe_line', 'guards_result', 'ended', 'ready'):
            self.assertIn('portrait_crop_api::' + hook, native)
        self.assertIn('fn cancel_portrait_crop_read', native)
        self.assertIn('"cmd":"portrait_crop_cancel"', native)
        self.assertIn('portrait_crop_api::enqueue(handle, cmd)', self.text('ui/src-tauri/src/native_dispatch.rs'))

    def test_source_caps(self):
        for path, cap in (('ui/src/App.tsx', 2160), ('ui/src-tauri/src/main.rs', 2060),
                          ('engine/src/lumaretouch_engine/server.py', 7065)):
            self.assertLessEqual(len(self.text(path).splitlines()), cap)
