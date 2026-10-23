# SPDX-License-Identifier: GPL-3.0-or-later
"""Authored integration fixtures, UNRUN. No inference or photograph quality claim."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from lumaretouch_engine import scope as SC
from lumaretouch_engine import semantic_colour_scope as C,semantic_colour_state as S
from lumaretouch_engine import semantic_colour_batch_ledger as L
from lumaretouch_engine.semantic_colour_batch_target import owned_key
from lumaretouch_engine.document_versions import DocumentVersions
from test_semantic_colour_portable import recipe


class ScopeContracts(unittest.TestCase):
    def test_registered_intent_has_dedicated_transport_not_generic_copy(self):
        row=next(x for x in SC.describe() if x['operation_id']==S.OP)
        self.assertTrue(row['transferable']);self.assertEqual(row['dedicated_transport'],'semantic_colour')
        self.assertEqual(SC.check_scope([S.OP]),[S.OP])
        value=C.params_of({S.KEY:recipe()})
        self.assertEqual(set(value),{'intent'})
        self.assertNotIn('target',value['intent']);self.assertNotIn('masks',value['intent'])
    def test_generic_install_refuses_without_mutating_target(self):
        target={'manual_exposure':.8};before=deepcopy(target)
        with self.assertRaises(ValueError):C.install(target,C.params_of({S.KEY:recipe()}))
        self.assertEqual(target,before)
    def test_generic_module_apply_cannot_copy_fitted_parameters(self):
        target={'manual_exposure':.8};before=deepcopy(target)
        with self.assertRaises(ValueError):SC.apply_modules(target,{S.OP:C.params_of({S.KEY:recipe()})})
        self.assertEqual(target,before)
    def test_text_preset_cannot_silently_omit_reference_photo(self):
        doc={'schema':SC.PRESET_SCHEMA,'id':'semantic-test','name':'test','kind':'color',
            'modules':{S.OP:C.params_of({S.KEY:recipe()})}}
        with self.assertRaisesRegex(SC.ScopeError,'便携预设'):SC.validate_preset(doc)
    def test_scope_restore_preserves_unrelated_fields(self):
        old={S.KEY:S.empty(),C.FIELDS[1]:None,C.FIELDS[2]:{},'manual':12}
        current={**old,'manual':15};current[S.KEY]=deepcopy(old[S.KEY]);current[S.KEY]['strengths']=[50.,70.,90.]
        restored=SC.restore_modules(current,old,[S.OP])
        self.assertEqual(restored[S.KEY],old[S.KEY]);self.assertEqual(restored['manual'],15)


class InspectionContracts(unittest.TestCase):
    def fixture(self):
        before={S.KEY:S.empty(),C.FIELDS[1]:None,C.FIELDS[2]:{}}
        after=deepcopy(before);after[S.KEY]['strengths']=[50.,70.,90.]
        row={'path':'synthetic-not-opened','state':before};versions=DocumentVersions();ident=versions.version(row).document_id
        owner=SimpleNamespace(documents=SimpleNamespace(rows=lambda:[row],current_index=lambda:-1,remember_current=lambda:None),
            editor=SimpleNamespace(capture=lambda:row['state']),versions=versions,ledger={},semantic_colour_inspection={
                'kind':'commit','review_token':'a'*32,'targets':[{'document_id':ident,'path':row['path'],'before':owned_key(before),'after':owned_key(after)}]})
        return owner,row,after
    def test_inspection_compares_every_target_without_inference(self):
        owner,row,after=self.fixture()
        self.assertEqual(L.inspect(owner)['inspection']['targets'][0]['state'],'before')
        row['state']=after
        self.assertEqual(L.inspect(owner)['inspection']['targets'][0]['state'],'after')
        row['state']=deepcopy(after);row['state'][S.KEY]['strengths']=[0.,0.,0.]
        self.assertEqual(L.inspect(owner)['inspection']['targets'][0]['state'],'different')
    def test_missing_target_never_becomes_success(self):
        owner,row,after=self.fixture();row['path']='another-file'
        self.assertEqual(L.inspect(owner)['inspection']['targets'][0]['state'],'missing')
    def test_cancelled_inspection_never_claims_all_targets_checked(self):
        owner,_,_=self.fixture()
        with self.assertRaises(InterruptedError):L.inspect(owner,cancelled=lambda:True)


class ReceiptContracts(unittest.TestCase):
    def test_nested_uncertainty_is_not_a_successful_host_receipt(self):
        from lumaretouch_engine.semantic_colour_host import SemanticColourHost
        host=SemanticColourHost();events=[];calls=[]
        engine=SimpleNamespace(_cancel_snapshot=lambda reason:None,_close_owned_previews=lambda:None)
        owner=SimpleNamespace(write_started=False)
        def execute(request,**kwargs):
            calls.append(request);owner.write_started=True
            return {'success':False,'outcome_unknown':True,'error':'synthetic publication failure','preflight_token':'a'*32}
        owner.execute=execute
        message={'cmd':'semantic_colour','request_id':'fixture_unknown','action':'request','request':{'action':'batch_apply'}}
        with patch('lumaretouch_engine.semantic_colour_controller.controller',return_value=owner):
            host.handle(engine,message,events.append)
            host.handle(engine,message,events.append)
        self.assertEqual(len(calls),1)
        self.assertFalse(events[0]['success']);self.assertTrue(events[0]['outcome_unknown'])
        self.assertIsNone(events[0]['committed']);self.assertEqual(events[0]['result']['preflight_token'],'a'*32)
        self.assertEqual(events[0],events[1])


class ExportRecoveryContracts(unittest.TestCase):
    def fixture(self):
        from lumaretouch_engine.semantic_colour_workflow import Workflow
        engine=SimpleNamespace(_document_versions=lambda:SimpleNamespace(workspace='retained-workspace'))
        workflow=Workflow(SimpleNamespace(engine=engine))
        request={'action':'preset_export_status','export_id':'a'*32,'path':'synthetic-not-opened.lrtcolour',
                 'expected':{'file_bytes':42,'file_sha256':'b'*64}}
        return workflow,request
    def test_exact_file_readback_survives_missing_temporary_artifact(self):
        workflow,request=self.fixture()
        with patch('lumaretouch_engine.semantic_colour_preset._file_identity',return_value=request['expected']):
            self.assertEqual(workflow.execute(request)['state'],'matching')
        self.assertEqual(workflow.exports,{})
    def test_retained_artifact_refuses_changed_receipt_without_reading_file(self):
        workflow,request=self.fixture();workflow.exports[request['export_id']]=SimpleNamespace(metadata={'file_bytes':43,'file_sha256':'b'*64})
        with patch('lumaretouch_engine.semantic_colour_preset._file_identity') as reader:
            with self.assertRaises(ValueError):workflow.execute(request)
            reader.assert_not_called()
    def test_missing_file_is_not_a_successful_write(self):
        workflow,request=self.fixture()
        with patch('lumaretouch_engine.semantic_colour_preset._file_identity',side_effect=FileNotFoundError):
            self.assertEqual(workflow.execute(request)['state'],'missing')
