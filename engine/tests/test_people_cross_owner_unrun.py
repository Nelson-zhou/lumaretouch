"""UNRUN source fixtures: reviewed replica ownership, mutation and copy contracts.

No test execution, product imports or inference were performed during authoring.
"""
from copy import deepcopy
import unittest
from lumaretouch_engine import people_state as S, people_cross_owner as C
from lumaretouch_engine import people_associations as G


def fixture():
    state=S.empty()
    evidence={'backend':'fixture','detector_model_sha256':'d'*64,'semantic_model_sha256':None,
              'landmark_digest':'e'*64,'status':'verified','source_width':128,'source_height':128,
              'orientation':'exif_normalized_once'}
    face=S.new_face('a'*64,[.1,.1,.6,.6],evidence)
    state['faces'][face['face_instance_id']]=face
    members=[{'document_id':'doc-a','scope_id':'doc-a','original_sha256':'a'*64,'ref':S.face_ref(face)},
             {'document_id':'doc-b','scope_id':'doc-b','original_sha256':'b'*64,
              'ref':{'asset_sha256':'b'*64,'face_instance_id':'face-b','analysis_revision':0}}]
    capsule=C.descriptor('association-a','doc-a',members,[{'op':'lnx.deform.v1','path':'/slim_face','value':.2}])
    return state,face,capsule


class ReviewedReplicaContract(unittest.TestCase):
    def test_canonical_generation_excludes_local_owner(self):
        _,_,capsule=fixture()
        other=C.descriptor(capsule['association_id'],'doc-b',list(reversed(capsule['members'])),capsule['intent'])
        self.assertEqual(capsule['generation'],other['generation'])
        self.assertNotEqual(capsule['local_document_id'],other['local_document_id'])

    def test_exact_owner_and_no_ordinary_mutation(self):
        state,face,capsule=fixture(); state=C.create(state,'person-a',capsule)
        self.assertEqual(C.validate_owner(state,'a'*64,'doc-a'),{'person-a'})
        with self.assertRaises(ValueError):C.validate_owner(state,'a'*64,'same-byte-copy')
        with self.assertRaises(ValueError):S.set_override(state,'person','person-a','lnx.deform.v1','/slim_face',.4)
        with self.assertRaises(ValueError):S.set_override(state,'person','person-a','lnx.deform.v1','/slim_face',None,unset=True)
        state,ordinary=G.create_person(state)
        with self.assertRaises(ValueError):G.set_link(state,face['face_instance_id'],ordinary,'confirmed',user_confirmed=True)

    def test_tamper_stale_ref_and_member_replacement_refuse(self):
        state,face,capsule=fixture(); state=C.create(state,'person-a',capsule)
        tampered=deepcopy(state); tampered['overrides'][0]['value']=.5
        with self.assertRaises(ValueError):S.check(tampered)
        stale=deepcopy(state); stale['faces'][face['face_instance_id']]['analysis_revision']+=1
        with self.assertRaises(ValueError):S.check(stale)
        members=deepcopy(capsule['members']); members[1]['document_id']='doc-c'; members[1]['scope_id']='doc-c'
        replacement=C.descriptor(capsule['association_id'],'doc-a',members,capsule['intent'])
        with self.assertRaises(ValueError):C.update(state,'person-a',replacement)

    def test_update_preserves_face_overrides_and_unlink_keeps_faces(self):
        state,face,capsule=fixture(); state=C.create(state,'person-a',capsule)
        state=S.set_override(state,'face',face['face_instance_id'],'lnx.deform.v1','/slim_face',.7)
        replacement=C.descriptor(capsule['association_id'],'doc-a',capsule['members'],
                                 [{'op':'lnx.deform.v1','path':'/slim_face','value':.4}])
        updated=C.update(state,'person-a',replacement); removed=C.unlink(updated,'person-a')
        self.assertEqual(removed['faces'],state['faces'])
        self.assertEqual([entry['value'] for entry in removed['overrides']],[.7])
        self.assertEqual(removed['persons'],{}); self.assertEqual(removed['links'],[])
        self.assertGreater(removed['association_revision'],state['association_revision'])

    def test_copy_detaches_and_materializes_only_inherited_winners(self):
        state,face,capsule=fixture(); state=C.create(state,'person-a',capsule)
        detached=C.detach_copy(state)
        self.assertEqual(detached['persons'],{}); self.assertEqual(detached['links'],[])
        self.assertEqual(detached['overrides'][0]['scope'],'face')
        self.assertEqual(detached['overrides'][0]['value'],.2)
        self.assertEqual(detached['faces'],state['faces'])
        explicit=S.set_override(state,'face',face['face_instance_id'],'lnx.deform.v1','/slim_face',.7)
        self.assertEqual([entry['value'] for entry in C.detach_copy(explicit)['overrides']],[.7])
        self.assertIn('person-a',state['persons'])

    def test_duplicate_scope_nonfinite_and_noncanonical_refuse(self):
        _,_,capsule=fixture(); members=deepcopy(capsule['members'])
        for member in members:member['scope_id']='project'
        with self.assertRaises(ValueError):C.descriptor('association-a','doc-a',members,capsule['intent'])
        with self.assertRaises(ValueError):C.descriptor('association-a','doc-a',capsule['members'],
            [{'op':'lnx.deform.v1','path':'/slim_face','value':float('nan')}])
        unordered=deepcopy(capsule); unordered['members'].reverse()
        with self.assertRaises(ValueError):C.check_descriptor(unordered)

    def test_reanalysis_requires_explicit_atomic_unlink_first(self):
        state,face,capsule=fixture(); state=C.create(state,'person-a',capsule)
        with self.assertRaises(ValueError):
            G.reanalyse(state,'a'*64,{face['face_instance_id']:face['evidence']},
                        expected_revision=state['revision'],user_confirmed=True)
        self.assertEqual(state['faces'][face['face_instance_id']]['analysis_revision'],0)
        detached=C.unlink(state,'person-a')
        refreshed=G.reanalyse(detached,'a'*64,{face['face_instance_id']:face['evidence']},
                             expected_revision=detached['revision'],user_confirmed=True)
        self.assertEqual(refreshed['faces'][face['face_instance_id']]['analysis_revision'],1)
