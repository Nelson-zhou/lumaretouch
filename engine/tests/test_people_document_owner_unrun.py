"""UNRUN owner transport fixtures; no rendering, model or runtime acceptance.

Authored only. Product imports and these tests were not executed during work.
"""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from lumaretouch_engine import people_document_owner as O
from lumaretouch_engine import people_state as S, people_cross_owner as C
from lumaretouch_engine import creative_derived_effects as D


def replica():
    state=S.empty()
    evidence={'backend':'fixture','detector_model_sha256':'d'*64,'semantic_model_sha256':None,
              'landmark_digest':'e'*64,'status':'verified','source_width':128,'source_height':128,
              'orientation':'exif_normalized_once'}
    face=S.new_face('a'*64,[.1,.1,.6,.6],evidence)
    state['faces'][face['face_instance_id']]=face
    members=[{'document_id':'doc-a','scope_id':'doc-a','original_sha256':'a'*64,'ref':S.face_ref(face)},
             {'document_id':'doc-b','scope_id':'doc-b','original_sha256':'b'*64,
              'ref':{'asset_sha256':'b'*64,'face_instance_id':'face-b','analysis_revision':0}}]
    descriptor=C.descriptor('association','doc-a',members,
        [{'op':'lnx.deform.v1','path':'/slim_face','value':.2}])
    return C.create(state,'replica',descriptor)


class DocumentOwnership(TestCase):
    def setUp(self):
        self.a={'document_id':'doc-a','path':'/same.png','state':{}}
        self.b={'document_id':'doc-b','path':'/same.png','state':{}}
        self.engine=SimpleNamespace(_docs=[self.a,self.b],_doc_index=0,
            _document_versions=lambda:SimpleNamespace(version=lambda row:SimpleNamespace(document_id=row['document_id'])))

    def test_same_path_parked_state_is_not_current_document(self):
        self.assertEqual(O.capture(self.engine,self.b['state'],'/same.png'),'doc-b')

    def test_context_candidate_requires_explicit_owner(self):
        self.assertIsNone(O.capture(self.engine,{},'/same.png',context_supplied=True))
        self.assertEqual(O.capture(self.engine,{},'/same.png',context_supplied=True,document_id='doc-b'),'doc-b')
        with self.assertRaises(ValueError):O.capture(self.engine,{},'/same.png',document_id='missing')
        with self.assertRaises(ValueError):O.capture(self.engine,{},'/other.png',document_id='doc-b')

    def test_original_snapshot_cannot_choose_capsule_owner(self):
        people={'state':replica(),'asset_sha256':'a'*64,'document_id':'doc-a'}
        O.validate_snapshot(people,'doc-a')
        with self.assertRaises(ValueError):O.validate_snapshot(people,'doc-b')
        # Rewriting the outer portrait field still cannot rewrite the capsule.
        people['document_id']='doc-b'
        with self.assertRaises(ValueError):O.validate_snapshot(people,'doc-b')

    def test_missing_owner_cannot_replay_cross_owner_graph(self):
        with self.assertRaises(ValueError):
            O.validate_snapshot({'state':replica(),'asset_sha256':'a'*64},None)

    def test_derived_admission_has_exact_same_byte_owner(self):
        state=replica(); source={'sha256':'a'*64,'width':128,'height':128}
        D.require_graph(state,source,document_id='doc-a')
        with self.assertRaises(ValueError):D.require_graph(state,source,document_id='doc-b')
        with self.assertRaises(ValueError):D.require_graph(state,source)

    def test_original_export_verifies_owner_before_reading_source(self):
        from lumaretouch_engine.people_export import verify_source
        snapshot={'people':{'state':replica(),'asset_sha256':'a'*64,'document_id':'doc-a'},
                  'people_document_id':'doc-b'}
        with patch('lumaretouch_engine.local_mask_state.source_digest',side_effect=AssertionError('Must refuse before source access')):
            with self.assertRaises(ValueError):verify_source(snapshot,'/same.png')

    def test_neutral_replica_cannot_bypass_export_admission(self):
        from lumaretouch_engine.people_export import fastpath_blocker
        state=replica(); capsule=state['persons']['replica']['cross_owner']
        neutral=C.descriptor(capsule['association_id'],'doc-a',capsule['members'],
            [{'op':'lnx.deform.v1','path':'/slim_face','value':0.}])
        state=C.update(state,'replica',neutral)
        self.assertTrue(fastpath_blocker({'state':state,'asset_sha256':'a'*64,'document_id':'doc-a'}))
