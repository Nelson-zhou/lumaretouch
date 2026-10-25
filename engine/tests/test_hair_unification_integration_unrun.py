# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored static integration specifications, never executed here. UNRUN."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding='utf-8')


class HairUnificationIntegration(unittest.TestCase):
    def test_independent_version_and_single_source_stage(self):
        state = source('engine/src/lumaretouch_engine/hair_unification_state.py')
        self.assertIn("'lnx.hair_unification.v1'", state)
        self.assertIn("'LNX-REF-PC-32472-C-fb2fe59a22'", state)
        pipeline = source('engine/src/lumaretouch_engine/vram.py')
        old = pipeline.index("source_effect(self,'hair_colour',out)")
        new = pipeline.index("source_effect(self,'hair_unification',out)")
        self.assertLess(old, new)
        self.assertEqual(pipeline.count("source_effect(self,'hair_unification',out)"), 1)

    def test_original_and_derived_snapshots_keep_owned_samples(self):
        host = source('engine/src/lumaretouch_engine/people_host.py')
        self.assertIn('capture_unification(retained_host,state,result,pc,source)', host)
        self.assertIn('capture_unification(retained_host,result,pc,binding,source_path=source_path)', host)
        export = source('engine/src/lumaretouch_engine/people_engine_runtime.py')
        self.assertIn('source_inputs.update(unification_inputs(snapshot))', export)
        context = source('engine/src/lumaretouch_engine/virtual_copy_people.py')
        self.assertIn("'hair_unification_assets': '_hair_unification_assets'", context)
        self.assertIn("value = {**value, 'hair_unification_assets': {}}", context)

    def test_full_review_bank_is_append_only_and_generic_active_patch_is_fenced(self):
        render = source('engine/src/lumaretouch_engine/full_candidate_render.py')
        self.assertIn("for bank in ('people_support_assets', 'hair_unification_assets')", render)
        self.assertIn("staged[bank].get(key)!=value", render)
        host = source('engine/src/lumaretouch_engine/people_host.py')
        self.assertIn('require_hair_unification_transition(self,before,candidate)', host)
        server = source('engine/src/lumaretouch_engine/server.py')
        self.assertIn("('lens_blur', 'light_glow', 'creative_selection', 'hair_unification')", server)
        self.assertIn('self.finish_hair_unification(msg, None)', server)

    def test_native_raw_receipt_cannot_settle_unvalidated_publication(self):
        native = source('ui/src-tauri/src/engine.rs')
        self.assertIn('hair_unification_api::observe_line(inspection_epoch, &line)', native)
        self.assertIn('hair_unification_api::guards_result(inspection_epoch,id)', native)
        self.assertIn('v["event"] != "hair_unification_result"', native)
        self.assertIn('"hair_unification_result" => {},', native)

    def test_persistent_union_and_legacy_digest_are_not_silently_changed(self):
        virtual = source('engine/src/lumaretouch_engine/virtual_copy_people.py')
        self.assertIn("'people_support_assets', 'hair_colour_assets', 'hair_unification_assets', 'hair_colour_evidence'", virtual)
        digest = source('engine/src/lumaretouch_engine/people_source_context.py')
        self.assertIn("defaults.pop('lnx.hair_unification.v1',None)", digest)
        replay = source('engine/src/lumaretouch_engine/hair_colour_replay.py')
        self.assertIn('if operation not in (H.OPERATION, U.OP)', replay)
        self.assertIn("reference['semantic_evidence_sha256'] != semantic_id", replay)

    def test_generic_target_candidates_cannot_bypass_image_review(self):
        candidate = source('engine/src/lumaretouch_engine/people_candidate_render.py')
        self.assertIn('require_hair_unification_transition(engine,row_snapshot(engine,row),candidate,row=row)', candidate)
        transfer = source('engine/src/lumaretouch_engine/people_transfer_adapter.py')
        self.assertIn('require_unreviewed_transition(target_state,out)', transfer)

    def test_packaging_and_modular_caps(self):
        packaging = source('packaging/stage-engine.sh')
        self.assertIn('core/hair_unification/build_hair_unification.sh', packaging)
        self.assertIn('bin/liblrt_hair_unification.so', packaging)
        for name, limit in [('ui/src/App.tsx', 2160), ('ui/src-tauri/src/main.rs', 2060),
                            ('engine/src/lumaretouch_engine/server.py', 7065)]:
            self.assertLessEqual(len(source(name).splitlines()), limit)

    def test_unknown_recovery_is_explicit_and_native_owned(self):
        ui = source('ui/src/hairUnification/HairRecovery.tsx')
        self.assertIn("runProject('open', {path, force: true})", ui)
        self.assertIn('!confirmed', ui)
        self.assertIn('onStartEngine()', ui)
        panel = source('ui/src/hairUnification/HairUnificationPanel.tsx')
        self.assertIn('data-hair-unification-workflow', panel)
        self.assertIn('port.dismissReopened()', panel)
        native = source('ui/src-tauri/src/hair_unification_api.rs')
        self.assertIn('workspace_reopened', native)
        self.assertIn('self.epoch != epoch || self.ended', native)
        self.assertIn('filter(|row| !row.settled)', native)


if __name__ == '__main__':
    unittest.main()
