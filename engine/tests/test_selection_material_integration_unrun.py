# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored source-route acceptance fixtures. UNRUN, no product imports needed."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[2]


def source(name):
    return (ROOT / name).read_text(encoding='utf-8')


class SelectionMaterialIntegration(unittest.TestCase):
    def test_serialized_creative_history_not_generic_double_owner(self):
        server = source('engine/src/lumaretouch_engine/server.py')
        self.assertIn("('lens_blur', 'light_glow', 'creative_selection')", server)
        self.assertIn('CreativeModuleCommandsMixin', server)
        family = source('engine/src/lumaretouch_engine/creative_selection_host.py')
        self.assertIn("commit_document(deepcopy(after), deepcopy(before), 'creative:selection_mask')", family)
        self.assertIn("if after['source_asset'] != before['source_asset']", family)

    def test_read_control_ingress_and_dispatch_rejection_settle_original(self):
        ingress = source('engine/src/lumaretouch_engine/read_job_ingress.py')
        self.assertIn('selection_jobs(engine).ingress(line)', ingress)
        self.assertIn('selection_jobs(engine).stop()', ingress)
        self.assertIn('engine._background_material_host().observe_line(line)', ingress)
        family = ast.parse(source('engine/src/lumaretouch_engine/creative_selection_host.py'))
        rejected = next(node for node in family.body if isinstance(node, ast.FunctionDef) and node.name == 'dispatch_rejected')
        self.assertTrue(any(isinstance(node, ast.Attribute) and node.attr == 'settle_cancels' for node in ast.walk(rejected)))

    def test_id_consumer_uses_original_decoder_bundle_and_existing_ownership(self):
        family = source('engine/src/lumaretouch_engine/id_background_controller.py')
        self.assertIn("'id_import_material':{'selection'}", family)
        self.assertIn("asset=resolve_for_id_background(p['selection'])", family)
        self.assertIn('bundle=A.pack(asset)', family)
        self.assertIn("('id_set','id_import','id_import_material','id_review')", family)
        self.assertIn("e._history_record('id_background:'+rid,before,coalesce=False)", family)
        resolver = source('engine/src/lumaretouch_engine/background_material_selection.py')
        self.assertIn("A.read(str(path), expected=row['binding'], cancelled=cancelled)", resolver)
        self.assertIn('current = S.match_selection(catalog, selection)', resolver)

    def test_source_only_caps_and_packaged_selection(self):
        for name, cap in [('ui/src/App.tsx', 2160), ('ui/src-tauri/src/main.rs', 2060),
                          ('engine/src/lumaretouch_engine/server.py', 7065)]:
            self.assertLessEqual(len(source(name).splitlines()), cap)
        stage = source('packaging/stage-engine.sh')
        self.assertIn('core/creative_selection/build_creative_selection.sh', stage)
        self.assertIn('bin/liblumaretouch_creative_selection.so', stage)

    def test_unknown_recovery_has_start_and_confirmed_saved_project_escape(self):
        recovery = source('ui/src/creativeLayers/SelectionRecovery.tsx')
        self.assertIn('onStartEngine().finally', recovery)
        self.assertIn("runProject('open', {path, force: true})", recovery)
        self.assertIn('!confirmed || choosing.current || !engineAlive', recovery)
        native = source('ui/src-tauri/src/creative_selection_api.rs')
        self.assertIn('"workspace_reopened":true', native)
        self.assertIn('row.mask.as_ref().is_some_and', native)
        self.assertNotIn('s.rows.clear()', native)

    def test_material_caller_checked_after_pending_curve_settlement(self):
        hook = source('ui/src/idBackground/useIdBackground.ts')
        settle = hook.index('await settleCurveEdit()')
        frozen = hook.index('if(frozenCaller&&')
        send = hook.index("'id_background_request'")
        self.assertLess(settle, frozen)
        self.assertLess(frozen, send)
        self.assertIn('recipe_document_id!==fence?.recipe_document_id', hook)


if __name__ == '__main__':
    unittest.main()
