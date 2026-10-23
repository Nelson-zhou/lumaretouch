"""UNRUN coordinator fixtures. No product imports or tests run during authoring."""
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from lumaretouch_engine import people_cross_owner_workflow as W
from lumaretouch_engine import people_cross_owner as C, people_state as S


def fixture():
    endpoints = []
    for index, letter in enumerate(('a', 'b')):
        graph = S.empty()
        evidence = {'backend': 'fixture', 'detector_model_sha256': 'd' * 64,
                    'semantic_model_sha256': None, 'landmark_digest': 'e' * 64,
                    'status': 'verified', 'source_width': 128, 'source_height': 128,
                    'orientation': 'exif_normalized_once'}
        face = S.new_face(letter * 64, [.1, .1, .6, .6], evidence)
        graph['faces'][face['face_instance_id']] = face
        proof = {'document': {'document_id': 'doc-' + letter, 'epoch': 'workspace', 'revision': 0},
                 'people_scope': 'doc-' + letter, 'state_revision': 0, 'association_revision': 0,
                 'graph_sha256': W.I.graph_digest(graph), 'source_proof': {'asset_sha256': letter * 64,
                 'original_sha256': letter * 64, 'creative_source': None}}
        ref = S.face_ref(face)
        endpoints.append({'index': index, 'row': {'path': letter + '.png', 'document_id': 'doc-' + letter},
                          'before': graph, 'proof': proof, 'ref': ref,
                          'member': {'document_id': 'doc-' + letter, 'scope_id': 'doc-' + letter,
                                     'original_sha256': letter * 64, 'ref': ref}})
    request = {'target_policy': 'persistent_association', 'operation': 'create', 'association_id': 'association',
               'source_ref': endpoints[0]['ref'], 'selection': {'lnx.deform.v1': ['/slim_face']},
               'source': endpoints[0]['proof'], 'targets': [{'target': endpoints[1]['proof'], 'target_refs': [endpoints[1]['ref']]}]}
    return endpoints, request


def prepare_fixture(endpoints, request):
    rows = [item['row'] for item in endpoints]
    versions = SimpleNamespace(version=lambda row: SimpleNamespace(document_id=row['document_id']))
    engine = SimpleNamespace(_batch_controller=lambda: SimpleNamespace(documents=SimpleNamespace(rows=lambda: rows)),
                             _document_versions=lambda: versions)
    by_id = {item['row']['document_id']: item for item in endpoints}
    def endpoint(_engine, _rows, proof, ref):
        item = deepcopy(by_id[proof['document']['document_id']])
        if item['proof'] != proof or item['ref'] != ref: raise ValueError('stale fixture endpoint')
        return item
    with patch.object(W, '_endpoint', side_effect=endpoint), patch.object(W.I, 'verify'), \
         patch.object(W.SOURCE, 'verify_row'), patch.object(W.V, 'row_snapshot', return_value={}):
        return W.prepare(engine, request, validate=False)


class PersistentWorkflow(TestCase):
    def test_exact_selection_and_one_face_per_document(self):
        _, request = fixture()
        self.assertEqual(W.options(request, ['lnx.deform.v1']), request)
        duplicate = deepcopy(request); duplicate['targets'][0]['target_refs'] *= 2
        with self.assertRaises(ValueError): W.options(duplicate, ['lnx.deform.v1'])
        with self.assertRaises(ValueError): W.options(request, [])

    def test_unlink_is_explicit_without_selected_values(self):
        _, request = fixture(); request['operation'] = 'unlink'; request['selection'] = {}
        self.assertEqual(W.options(request, [])['operation'], 'unlink')
        request['selection'] = {'lnx.deform.v1': ['/slim_face']}
        with self.assertRaises(ValueError): W.options(request, ['lnx.deform.v1'])

    def test_create_person_intent_does_not_copy_face_overrides(self):
        endpoints, request = fixture()
        graph = endpoints[0]['before']; face_id = endpoints[0]['ref']['face_instance_id']
        endpoints[0]['before'] = S.set_override(graph, 'face', face_id, 'lnx.deform.v1', '/slim_face', .3)
        staged, review = prepare_fixture(endpoints, request)
        self.assertEqual(review['intent'], [{'op': 'lnx.deform.v1', 'path': '/slim_face', 'value': .3}])
        for item in staged:
            self.assertEqual(item['candidate']['faces'], item['before']['faces'])
            self.assertEqual(item['candidate']['persons']['association']['cross_owner']['generation'], review['generation'])
        self.assertEqual({leaf['scope'] for leaf in staged[1]['candidate']['overrides']}, {'person'})
        self.assertEqual({leaf['scope'] for leaf in staged[0]['candidate']['overrides']}, {'person', 'face'})

    def test_patch_no_change_refuses_and_unlink_removes_all_replicas(self):
        endpoints, request = fixture(); created, _ = prepare_fixture(endpoints, request)
        for endpoint, item in zip(endpoints, created): endpoint['before'] = item['candidate']
        request['operation'] = 'patch'
        with self.assertRaisesRegex(ValueError, 'do not change'): prepare_fixture(endpoints, request)
        request['operation'] = 'unlink'; request['selection'] = {}
        removed, review = prepare_fixture(endpoints, request)
        self.assertTrue(review['intent'])
        for item in removed:
            self.assertEqual(item['candidate']['persons'], {})
            self.assertEqual(item['candidate']['links'], [])
            self.assertEqual(item['candidate']['faces'], item['before']['faces'])

    def test_inconsistent_generation_refuses_without_partial_patch(self):
        endpoints, request = fixture(); created, _ = prepare_fixture(endpoints, request)
        for endpoint, item in zip(endpoints, created): endpoint['before'] = item['candidate']
        capsule = endpoints[1]['before']['persons']['association']['cross_owner']
        changed = C.descriptor('association', 'doc-b', capsule['members'],
                               [{'op': 'lnx.deform.v1', 'path': '/slim_face', 'value': .5}])
        endpoints[1]['before'] = C.update(endpoints[1]['before'], 'association', changed)
        request['operation'] = 'patch'
        with self.assertRaisesRegex(ValueError, 'disagree'): prepare_fixture(endpoints, request)

    def test_missing_saved_member_refuses_unlink(self):
        endpoints, request = fixture(); created, _ = prepare_fixture(endpoints, request)
        endpoints[0]['before'] = created[0]['candidate']
        request['operation'] = 'unlink'; request['selection'] = {}
        with self.assertRaisesRegex(ValueError, 'every|Every'): prepare_fixture(endpoints, request)

    def test_public_source_evidence_is_explicit(self):
        endpoints, request = fixture(); staged, _ = prepare_fixture(endpoints, request)
        source = W._public(staged[0], live=True)
        self.assertTrue(source['live']); self.assertEqual(source['document_id'], 'doc-a')
        self.assertEqual(set(source['association']), {'owner', 'ref', 'candidate_sha256', 'person_id'})
        self.assertNotIn('people_transfer', source)
