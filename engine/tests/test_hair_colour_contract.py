"""Authored-only contract fixtures. No local execution has occurred.

Constructed identities here test serialization/ownership, NOT real segmentation
quality, person detection, image acceptance or a model execution receipt.
"""
import copy
import unittest
from lumaretouch_engine import hair_colour_state as C, hair_colour_assets as A, people_state as P


def face_state():
    source = {'sha256': '1'*64, 'width': 128, 'height': 128}
    evidence = {'backend': 'mediapipe', 'detector_model_sha256': '2'*64,
        'semantic_model_sha256': A.MODEL_SHA256, 'landmark_digest': '3'*64,
        'status': 'verified', 'source_width': 128, 'source_height': 128, 'orientation': 'exif_normalized_once'}
    face = P.new_face(source['sha256'], [.2, .2, .8, .8], evidence)
    state = P.empty(); state['faces'][face['face_instance_id']] = face
    return state, P.face_ref(face), source


def stroke():
    return {'version': 1, 'domain': 'source-normalized', 'objects': [{
        'id': 'stroke', 'name': 'Contract fixture, not real hair', 'enabled': True, 'operation': 'add',
        'kind': 'brush', 'opacity': 1., 'feather': 1., 'points': [[.2,.2],[.3,.4]], 'axes': [[.03,0],[0,.03]]}]}


class HairContracts(unittest.TestCase):
    def test_neutral_is_exact_and_style_is_not_strength(self):
        self.assertFalse(C.active(None)); value = {**C.neutral(), 'style': 'moss_green'}
        self.assertFalse(C.active(value)); self.assertEqual(len(C.STYLES), 13)
        self.assertEqual(set(C.transferable(value)), {'version','style','strength','gloss'})

    def test_strict_amount_and_schema_rejections(self):
        for amount in (True, -1, 1.1, float('nan'), float('inf')):
            with self.assertRaises(ValueError): C.check({**C.neutral(), 'strength': amount})
        with self.assertRaises(ValueError): C.check({**C.neutral(), 'support': stroke()})
        with self.assertRaises(ValueError): C.check({**C.neutral(), 'style': 'commercial_lut'})

    def test_review_is_required_for_one_face_too(self):
        state, ref, source = face_state()
        with self.assertRaises(ValueError): A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=False)
        with self.assertRaises(ValueError): A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=1)
        record = A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        record['review']['confirmed'] = 1
        with self.assertRaises(ValueError): A.check(record)

    def test_exact_ownership_survives_retain_detach_and_undo_pointer(self):
        state, ref, source = face_state(); before = copy.deepcopy(state)
        record = A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        after, store = A.retain(state, {}, record)
        self.assertEqual(state, before); self.assertEqual(A.resolve(after, store, ref), record)
        detached = A.detach(after, ref)
        self.assertIsNone(A.resolve(detached, store, ref)); self.assertEqual(len(store), 1)
        self.assertEqual(A.resolve(after, store, ref), record) # Existing owner restores graph pointer, not pixels.

    def test_cross_photo_and_analysis_rebinding_rejected(self):
        state, ref, source = face_state()
        record = A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        after, store = A.retain(state, {}, record)
        altered = copy.deepcopy(after); face = altered['faces'][ref['face_instance_id']]
        face['analysis_revision'] += 1
        with self.assertRaises(ValueError): A.resolve(altered, store, P.face_ref(face))
        with self.assertRaises(ValueError): A.reviewed(ref, {**source, 'sha256': '9'*64}, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)

    def test_full_image_and_semantic_shortcuts_are_not_instances(self):
        full = {'id':'all','name':'all','enabled':True,'operation':'add','kind':'full','opacity':1.,'feather':0.}
        semantic = {**full, 'kind':'semantic', 'channel':'hair'}
        for obj in (full, semantic):
            with self.assertRaises(ValueError): A.mask({**A.empty_mask(), 'objects':[obj]})

    def test_source_or_model_change_rejected(self):
        state, ref, source = face_state()
        with self.assertRaises(ValueError): A.reviewed(ref, source, stroke(), '9'*64, evidence_sha='4'*64, confirmed=True)
        record = A.reviewed(ref, {**source,'width':127}, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        with self.assertRaises(ValueError): A.retain(state, {}, record)

    def test_recovery_preserves_support_and_only_changes_asset_reference(self):
        state, ref, source = face_state()
        record = A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        after, store = A.retain(state, {}, record)
        recovery = stroke(); recovery['objects'][0]['id'] = 'recover'
        changed = A.check({**record,'recovery':recovery})
        next_state, next_store = A.retain(after, store, changed)
        self.assertEqual(changed['support'], record['support']); self.assertEqual(len(next_store),2)
        self.assertEqual(next_state['overrides'], after['overrides'])
        self.assertEqual(A.resolve(after, next_store, ref), record)

    def test_changed_vectors_fail_retained_hash(self):
        state, ref, source = face_state()
        record = A.reviewed(ref, source, stroke(), A.MODEL_SHA256, evidence_sha='4'*64, confirmed=True)
        after, store = A.retain(state, {}, record)
        key = next(iter(store)); store[key]['support']['objects'][0]['points'][0][0] = .9
        with self.assertRaises(ValueError): A.resolve(after, store, ref)

    def test_rgb16_frozen_graph_never_bypasses_requested_hair(self):
        from lumaretouch_engine.people_export import fastpath_blocker
        state, ref, source = face_state()
        snapshot={'state':state,'asset_sha256':source['sha256']}
        self.assertFalse(fastpath_blocker(snapshot)) # A neutral census is not an edit.
        state['overrides']=[{'scope':'face','target_id':ref['face_instance_id'],
            'operation_id':C.OPERATION,'parameter_path':'/strength','value':.5}]
        self.assertTrue(fastpath_blocker(snapshot))
        state['overrides'][0]['operation_id']='unsupported.operation.v1'
        self.assertTrue(fastpath_blocker(snapshot)) # Checked renderer must refuse.

    def test_old_project_schema_cannot_hide_hair_intent_or_assets(self):
        from lumaretouch_engine.hair_colour_project import validate
        state, ref, _ = face_state()
        state['overrides']=[{'scope':'face','target_id':ref['face_instance_id'],
            'operation_id':C.OPERATION,'parameter_path':'/gloss','value':.2}]
        with self.assertRaises(ValueError):validate({'people_graph':state},allowed=False)
        with self.assertRaises(ValueError):validate({'hair_colour_assets':{}},allowed=False)


class RetainedHairEvidenceContract(unittest.TestCase):
    """Constructed lossless-codec fixtures, not segmentation/inference receipts."""
    def fixture(self):
        import hashlib
        import numpy as np
        _, _, source = face_state()
        weight = np.array([[0., .12345678], [.999999, 1.]], dtype=np.float32)
        return {'domain':'source-normalized', 'source':source, 'model_sha256':A.MODEL_SHA256,
            'producer':'mediapipe-six-class-confidence-gated-hair', 'weight':weight,
            'weight_sha256':hashlib.sha256(weight.tobytes()).hexdigest()}

    def test_lossless_bank_and_replay_without_precompute(self):
        from types import SimpleNamespace
        from lumaretouch_engine import hair_colour_evidence as E
        value = self.fixture(); bank, key = E.retain({}, value)
        engine = SimpleNamespace(_hair_colour_evidence=bank, _precompute=None)
        replay = E.current(engine, value['source'], None)
        self.assertEqual(replay['weight'].tobytes(), value['weight'].tobytes())
        self.assertEqual(E.identity(replay), key)

    def test_corruption_wrong_source_and_evidence_replacement_refused(self):
        import hashlib
        from lumaretouch_engine import hair_colour_evidence as E
        value = self.fixture(); bank, key = E.retain({}, value)
        corrupt = copy.deepcopy(bank); corrupt[key]['weight_sha256'] = '0'*64
        with self.assertRaises(ValueError): E.check_store(corrupt)
        with self.assertRaises(ValueError): E.for_source(bank, {**value['source'], 'width':127})
        changed = copy.deepcopy(value); changed['weight'][0,0] = .5
        changed['weight_sha256'] = hashlib.sha256(changed['weight'].tobytes()).hexdigest()
        with self.assertRaises(ValueError): E.retain(bank, changed)

    def test_declared_decode_bomb_is_rejected_before_decompression(self):
        from lumaretouch_engine import hair_colour_evidence as E
        packed = E.encode(self.fixture()); packed['shape'] = [65536,65536]
        with self.assertRaises(ValueError): E.decode(packed)
