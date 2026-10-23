"""UNRUN fixtures for existing-ledger atomic reviewed association boundaries.

Authored from source contracts only; not imported or executed during development.
"""
from copy import deepcopy
import unittest
from lumaretouch_engine import people_state as S, people_cross_owner as C
from lumaretouch_engine.people_cross_owner_ledger import validate_plans
from lumaretouch_engine.people_graph_patch import between, apply


def cohort():
    graphs={}; members=[]; targets={}
    evidence={'backend':'fixture','detector_model_sha256':'d'*64,'semantic_model_sha256':None,
              'landmark_digest':'e'*64,'status':'verified','source_width':128,'source_height':128,
              'orientation':'exif_normalized_once'}
    for index,(owner,asset) in enumerate((('doc-a','a'*64),('doc-b','b'*64))):
        graph=S.empty(); face=S.new_face(asset,[.1,.1,.6,.6],evidence)
        graph['faces'][face['face_instance_id']]=face; graphs[owner]=graph
        member={'document_id':owner,'scope_id':owner,'original_sha256':asset,'ref':S.face_ref(face)}
        members.append(member)
        targets[str(index)]={'document_id':owner,'people_scope':owner,'asset_sha256':asset,
            'source_proof':{'asset_sha256':asset,'original_sha256':asset},'reviewed_face_refs':[S.face_ref(face)]}
    intent=[{'op':'lnx.deform.v1','path':'/slim_face','value':.2}]
    plans={owner:{'row':{'document_id':owner},'before':graph,
        'candidate':C.create(graph,'person-a',C.descriptor('association-a',owner,members,intent))}
        for owner,graph in graphs.items()}
    return plans,targets


def advance(plans,action):
    result={}
    for owner,plan in plans.items():
        before=plan['candidate']; capsule=before['persons']['person-a']['cross_owner']
        if action=='patch':
            replacement=C.descriptor(capsule['association_id'],owner,capsule['members'],
                                     [{'op':'lnx.deform.v1','path':'/slim_face','value':.4}])
            candidate=C.update(before,'person-a',replacement)
        else:candidate=C.unlink(before,'person-a')
        result[owner]={'row':plan['row'],'before':before,'candidate':candidate}
    return result


class AtomicReviewedAssociationLedger(unittest.TestCase):
    def test_create_patch_unlink_and_protected_undo_candidates(self):
        creation,targets=cohort(); patch=advance(creation,'patch'); unlink=advance(patch,'unlink')
        for plans in (creation,patch,unlink):
            validate_plans(plans,targets)
            undo={owner:{'row':plan['row'],'before':plan['candidate'],
                         'candidate':apply(plan['candidate'],between(plan['before'],plan['candidate']),redo=False)}
                  for owner,plan in plans.items()}
            validate_plans(undo,targets)
            redo={owner:{'row':plan['row'],'before':undo[owner]['candidate'],
                         'candidate':apply(undo[owner]['candidate'],between(plan['before'],plan['candidate']),redo=True)}
                  for owner,plan in plans.items()}
            validate_plans(redo,targets)

    def test_omitted_member_in_create_patch_unlink_refuses(self):
        creation,targets=cohort()
        for plans in (creation,advance(creation,'patch'),advance(creation,'unlink')):
            with self.assertRaises(ValueError):validate_plans({'doc-a':plans['doc-a']},targets)
            with self.assertRaises(ValueError):validate_plans(plans,{'0':targets['0']})

    def test_wrong_source_original_or_reviewed_face_ref_refuses(self):
        plans,targets=cohort()
        for key in ('asset_sha256','original_sha256'):
            wrong=deepcopy(targets); wrong['1']['source_proof'][key]='f'*64
            with self.assertRaises(ValueError):validate_plans(plans,wrong)
        wrong=deepcopy(targets); wrong['1']['reviewed_face_refs'][0]['analysis_revision']+=1
        with self.assertRaises(ValueError):validate_plans(plans,wrong)
        wrong=deepcopy(targets); wrong['1']['people_scope']='doc-a'
        with self.assertRaises(ValueError):validate_plans(plans,wrong)

    def test_divergent_valid_generations_refuse(self):
        plans,targets=cohort(); graph=plans['doc-b']['candidate']; capsule=graph['persons']['person-a']['cross_owner']
        replacement=C.descriptor(capsule['association_id'],'doc-b',capsule['members'],
                                 [{'op':'lnx.deform.v1','path':'/slim_face','value':.6}])
        plans['doc-b']['candidate']=C.update(graph,'person-a',replacement)
        with self.assertRaises(ValueError):validate_plans(plans,targets)

    def test_face_edit_does_not_need_whole_cohort(self):
        plans,targets=cohort(); before=plans['doc-a']['candidate']; face_id=next(iter(before['faces']))
        candidate=S.set_override(before,'face',face_id,'lnx.deform.v1','/slim_face',.7)
        validate_plans({'doc-a':{'row':{'document_id':'doc-a'},'before':before,'candidate':candidate}},
                       {'0':targets['0']})
