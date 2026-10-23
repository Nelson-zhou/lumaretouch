"""Authored derived ID support/transaction contracts. UNRUN.

Mocks isolate source routing and transaction ownership, not image quality. These
fixtures are not evidence that Rust, SAM, GPU, export, or project QA has passed.
"""
from contextlib import ExitStack
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import numpy as np

from lumaretouch_engine import id_background_support as U
from lumaretouch_engine import id_background_state as S
from lumaretouch_engine import local_mask_state as M
from lumaretouch_engine import creative_derived_prompted as CP


SOURCE = {'sha256':'a'*64,'width':2,'height':2}


def radial(ident='subject'):
    return {'id':ident,'name':ident,'enabled':True,'operation':'add','kind':'radial',
            'opacity':1.,'feather':0.,'center':[.5,.5],'axes':[[.3,0],[0,.4]]}


def local(objects=None, source=None):
    value=M.empty()
    value['source']=deepcopy(SOURCE if source is None else source)
    value['recipe']['objects']=[radial()] if objects is None else deepcopy(objects)
    return M.check(value)


def reviewed(category='subject', objects=None):
    mask=local(objects)
    return U.check_binding({'version':1,'category':category,'reviewed':True,
                            'mask':mask,'recipe_sha256':U.digest(mask)},category)


def prompted(packet, enabled=True):
    obj={k:v for k,v in radial('prompted').items() if k not in ('center','axes')}
    obj.update(kind='prompted',enabled=enabled,selection={
        'prompts':{'points':[{'x':.5,'y':.5,'label':1}],'box':None},'candidate':1,
        'model':{'id':'sam2.1-tiny','checkpoint_sha256':'b'*64,'config_sha256':'c'*64,
                 'code_revision':'d'*40,'contract':'sam2.1-tiny-points-box-rgb8-longedge2048-fp32-v1'},
        'input_sha256':packet['descriptor']['input_sha256'],'device':'cpu'})
    return obj


def pixels():
    # Adjacent source values intentionally contain real sub-RGB8 precision.
    return np.array([[[256/65535,257/65535,258/65535],[.2,.3,.4]],
                     [[.45,.55,.65],[.8,.9,1.]]],dtype=np.float32)


class DerivedReviewContracts(TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.rgb=pixels()
        self.engine=SimpleNamespace(_local_masks=local(),_docs=[{'path':'/must-not-decode/original.png'}],
                                    _doc_index=0,_vram=SimpleNamespace(h=2,w=2))
        for name,value in (('binding',SOURCE),('record',{'id':'derived'}),('verify',SOURCE)):
            self.stack.enter_context(patch('lumaretouch_engine.creative_derived_source.'+name,return_value=value))
        self.preview=self.stack.enter_context(patch('lumaretouch_engine.creative_derived_id_background.preview',
                                                   return_value=(None,self.rgb,('current-source-and-pipeline',))))
        self.fields=self.stack.enter_context(patch('lumaretouch_engine.prompted_mask_resolver.fields',return_value={}))
        self.stack.enter_context(patch('lumaretouch_engine.prompted_mask_resolver.dependency_stamp',return_value=('actual-code','actual-checkpoint')))
        self.original=self.stack.enter_context(patch.object(M,'bind_source',side_effect=AssertionError('No original source binding')))

    def test_categories_remain_independent_and_copy_current_objects(self):
        value=S.empty();value['source']=deepcopy(SOURCE)
        for category in S.CATEGORIES:
            value['support'][category]=U.review(self.engine,category,['subject'],True)
            self.assertEqual(value['support'][category]['category'],category)
            self.assertEqual(value['support'][category]['mask'],local())
        S.check(value)
        self.engine._local_masks['recipe']['objects'][0]['center'][0]=.25
        self.assertEqual(value['support']['subject']['mask']['recipe']['objects'][0]['center'][0],.5)
        self.assertIsNot(value['support']['subject'],value['support']['contact'])
        self.original.assert_not_called()

    def test_boolean_receipt_version_is_not_a_canonical_review(self):
        value=reviewed();value['version']=True
        with self.assertRaises(ValueError):U.check_binding(value,'subject')

    def test_unreviewed_missing_duplicate_or_original_bound_selection_rejected(self):
        for ids,accepted in ((['subject'],False),([],True),(['subject','subject'],True),(['missing'],True),([{}],True)):
            with self.assertRaises(ValueError):U.review(self.engine,'subject',ids,accepted)
        self.engine._local_masks['source']['sha256']='f'*64
        with self.assertRaises(ValueError):U.review(self.engine,'subject',['subject'],True)

    def test_selected_composition_order_is_not_request_order(self):
        self.engine._local_masks=local([radial('first'),radial('second')])
        value=U.review(self.engine,'all',['second','first'],True)
        self.assertEqual([o['id'] for o in value['mask']['recipe']['objects']],['first','second'])

    def test_generic_semantic_and_full_masks_never_become_contact_or_hair(self):
        for obj in ({**{k:v for k,v in radial().items() if k not in ('center','axes')},'kind':'semantic','channel':'hair'},
                    {**{k:v for k,v in radial().items() if k not in ('center','axes')},'kind':'full'}):
            self.engine._local_masks=local([obj])
            with self.assertRaises(ValueError):U.review(self.engine,'contact',['subject'],True)

    def test_disabled_prompted_review_uses_canonical_packet_not_proxy(self):
        packet=CP.from_pixels(SOURCE,self.rgb)
        self.engine._local_masks=local([prompted(packet,enabled=False)])
        with patch.object(CP,'capture',return_value=packet) as capture:
            value=U.review(self.engine,'contact',['prompted'],True)
        capture.assert_called_once_with(self.engine)
        args,kwargs=self.fields.call_args
        self.assertIsNone(args[2]);self.assertEqual(args[1],SOURCE)
        self.assertIs(kwargs['source_input'],packet);self.assertTrue(kwargs['force'])
        self.assertTrue(args[0]['objects'][0]['enabled'])
        self.assertFalse(value['mask']['recipe']['objects'][0]['enabled'])

    def test_prompted_review_rejects_changed_input_or_changed_chosen_object(self):
        packet=CP.from_pixels(SOURCE,self.rgb)
        self.engine._local_masks=local([prompted(packet)])
        self.engine._local_masks['recipe']['objects'][0]['selection']['input_sha256']='f'*64
        with patch.object(CP,'capture',return_value=packet):
            with self.assertRaises(ValueError):U.review(self.engine,'subject',['prompted'],True)
        self.engine._local_masks=local([prompted(packet)])
        def mutate(*args,**kwargs):
            self.engine._local_masks['recipe']['objects'][0]['name']='Changed during resolution'
            return {}
        self.fields.side_effect=mutate
        with patch.object(CP,'capture',return_value=packet):
            with self.assertRaises(ValueError):U.review(self.engine,'subject',['prompted'],True)

    def test_native_review_still_uses_its_original_file_route(self):
        with patch('lumaretouch_engine.creative_derived_source.record',return_value=None), \
             patch('lumaretouch_engine.creative_derived_id_background.preview',side_effect=AssertionError('No derived preview')):
            U.review(self.engine,'subject',['subject'],True)
        self.assertEqual(self.fields.call_args.args[2],'/must-not-decode/original.png')
        self.assertNotIn('source_input',self.fields.call_args.kwargs)

    def test_changed_source_pipeline_key_cannot_accept_manual_review(self):
        self.preview.side_effect=[(None,self.rgb,('before',)),(None,self.rgb,('after',))]
        with self.assertRaises(ValueError):U.review(self.engine,'subject',['subject'],True)


class DerivedRasterContracts(TestCase):
    def setUp(self):
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.rgb=pixels();self.support=reviewed()
        self.fields=self.stack.enter_context(patch('lumaretouch_engine.prompted_mask_resolver.fields',return_value={}))
        self.raster=self.stack.enter_context(patch.object(U.R,'raster',return_value=np.array([[0,64],[128,255]],np.uint8)))
        self.verify_file=self.stack.enter_context(patch.object(M,'verify_source',side_effect=AssertionError('Derived path must not read original')))

    def test_manual_preview_needs_no_model_packet_or_model_install(self):
        with patch.object(CP,'capture',side_effect=AssertionError('No model work for manual masks')):
            result=U.raster(self.support,None,self.rgb,effective_source=SOURCE)
        self.assertEqual(result.dtype,np.float32)
        self.assertEqual(float(result[-1,-1]),1.)
        self.verify_file.assert_not_called()
        self.assertIs(self.raster.call_args.kwargs['rgb'],self.rgb)

    def test_fullfloat_export_passes_identical_pixels_and_preserves_low_bits(self):
        before=self.rgb.copy()
        U.raster(self.support,None,self.rgb,effective_source=SOURCE,full_source=True,source_pixels=self.rgb)
        self.assertIs(self.fields.call_args.kwargs['source_pixels'],self.rgb)
        self.assertIs(self.raster.call_args.kwargs['rgb'],self.rgb)
        self.assertTrue(self.fields.call_args.kwargs['force'])
        self.assertTrue(np.array_equal(self.rgb,before))
        self.assertNotEqual(self.rgb[0,0,0],self.rgb[0,0,1])

    def test_mixed_source_routes_and_proxy_export_fail_closed(self):
        for path,kwargs in (
            ('/original.png',{'effective_source':SOURCE}),
            (None,{}),
            (None,{'effective_source':{**SOURCE,'sha256':'f'*64}}),
            (None,{'effective_source':SOURCE,'full_source':True}),
            (None,{'effective_source':SOURCE,'full_source':True,'source_pixels':self.rgb.copy()}),
            (None,{'effective_source':SOURCE,'source_pixels':self.rgb}),
        ):
            with self.assertRaises(ValueError):U.raster(self.support,path,self.rgb,**kwargs)
        proxy=self.rgb[:1,:1]
        with self.assertRaises(ValueError):
            U.raster(self.support,None,proxy,effective_source=SOURCE,full_source=True,source_pixels=proxy)
        self.raster.assert_not_called()

    def test_live_prompted_requires_owned_packet_and_force_does_not_imply_full_source(self):
        packet=CP.from_pixels(SOURCE,self.rgb);support=reviewed(objects=[prompted(packet)])
        with self.assertRaises(ValueError):U.raster(support,None,self.rgb,effective_source=SOURCE)
        U.raster(support,None,self.rgb,effective_source=SOURCE,source_input=packet,force_prompted=True)
        self.assertIs(self.fields.call_args.kwargs['source_input'],packet)
        self.assertIsNone(self.fields.call_args.kwargs['source_pixels'])
        self.assertTrue(self.fields.call_args.kwargs['force'])

    def test_cancellation_and_invalid_float_source_never_rasterize(self):
        with self.assertRaises(InterruptedError):
            U.raster(self.support,None,self.rgb,effective_source=SOURCE,cancelled=lambda:True)
        for rgb in (self.rgb.astype(np.uint8),self.rgb.astype(np.float64),np.full((2,2,3),np.nan,np.float32),np.full((2,2,3),1.01,np.float32)):
            with self.assertRaises(ValueError):U.raster(self.support,None,rgb,effective_source=SOURCE)
        self.raster.assert_not_called()

    def test_native_raster_preserves_original_verification_and_full_source_flag(self):
        with patch.object(M,'verify_source') as original:
            U.raster(self.support,'/fixture/original.png',self.rgb,full_source=True)
        original.assert_called_once_with(self.support['mask'],'/fixture/original.png')
        self.assertEqual(self.fields.call_args.args[2],'/fixture/original.png')
        self.assertTrue(self.fields.call_args.kwargs['force'])
        self.assertIsNone(self.fields.call_args.kwargs['source_pixels'])


class DerivedTransactionContracts(TestCase):
    def setUp(self):
        from lumaretouch_engine.id_background_controller import Controller
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.version=SimpleNamespace(document_id='version-owner',revision=3)
        self.engine=SimpleNamespace(_load_id='load-owner',_docs=[{}],_doc_index=0,
            _id_background=S.empty(),_id_background_bundle=None,_bg={'active':False},
            _sky_replacement={'enabled':False},_vram=object())
        e=self.engine;e._document_versions=lambda:SimpleNamespace(version=lambda row:self.version)
        e._guard_editable=lambda purpose:None
        e._history_capture=Mock(side_effect=lambda:{'recipe':deepcopy(e._id_background),'bundle':deepcopy(e._id_background_bundle)})
        def restore(before):e._id_background,e._id_background_bundle=deepcopy(before['recipe']),deepcopy(before['bundle'])
        e._history_apply=Mock(side_effect=restore)
        e._fence_current_document=Mock();e._cancel_snapshot=Mock();e._history_record=Mock()
        e._write_current_frame=lambda purpose:{'event':'frame','purpose':purpose}
        e.doc_state=lambda:{};e._history_report=lambda:{'can_undo':True}
        self.events=[];self.owner=Controller(e,self.events.append)
        for name,value in (('binding',SOURCE),('record',{'id':'derived'}),('verify',SOURCE)):
            self.stack.enter_context(patch('lumaretouch_engine.creative_derived_source.'+name,return_value=value))
        self.stack.enter_context(patch('lumaretouch_engine.creative_derived_id_background.validate_state',side_effect=lambda owner:S.check(owner._id_background)))
        self.stack.enter_context(patch('lumaretouch_engine.creative_derived_id_background.validate',side_effect=lambda value,source:S.check(value)))
        self.sync=self.stack.enter_context(patch('lumaretouch_engine.id_background_runtime.sync'))
        self.stack.enter_context(patch('lumaretouch_engine.id_background_runtime.report',return_value={'available':True}))
        self.review=self.stack.enter_context(patch.object(U,'review',side_effect=lambda engine,category,ids,accepted:reviewed(category)))

    def request(self,action='id_review',rid='request-1',**extra):
        request={'cmd':'background','action':action,'request_id':rid,'document_id':'load-owner',
                 'recipe_document_id':'version-owner','recipe_revision':'3'}
        if action=='id_review':request.update(category='subject',object_ids=['subject'],reviewed=True)
        request.update(extra)
        return request

    def test_independent_review_updates_only_requested_category_then_replays_terminal_receipt(self):
        request=self.request(category='contact')
        self.owner.handle(request)
        self.assertTrue(self.events[-1]['success'])
        self.assertEqual(self.engine._id_background['source'],SOURCE)
        self.assertIsNone(self.engine._id_background['support']['subject'])
        self.assertIsNotNone(self.engine._id_background['support']['contact'])
        self.assertNotIn('presented',self.events[-1])
        self.engine._load_id='new-document';self.version.revision=4
        self.owner.handle(request)
        self.assertTrue(self.events[-1]['replayed']);self.assertTrue(self.events[-1]['success'])
        self.review.assert_called_once();self.engine._history_record.assert_called_once()

    def test_request_id_reuse_different_content_cannot_rewrite_review(self):
        self.owner.handle(self.request())
        self.owner.handle(self.request(category='all'))
        self.assertFalse(self.events[-1]['success'])
        self.assertIsNone(self.engine._id_background['support']['all'])
        self.review.assert_called_once()

    def test_version_change_during_review_is_rejected_before_history_or_mutation(self):
        def change(*args):
            self.version.revision=4
            return reviewed()
        self.review.side_effect=change
        self.owner.handle(self.request())
        self.assertFalse(self.events[-1]['success'])
        self.assertEqual(self.engine._id_background,S.empty())
        self.engine._history_capture.assert_not_called();self.sync.assert_not_called()

    def test_runtime_failure_restores_recipe_bundle_without_recording_history(self):
        self.sync.side_effect=[ValueError('support source changed'),None]
        self.owner.handle(self.request())
        self.assertFalse(self.events[-1]['success']);self.assertFalse(self.events[-1]['outcome_unknown'])
        self.assertEqual(self.engine._id_background,S.empty())
        self.engine._history_apply.assert_called_once();self.engine._history_record.assert_not_called()
        self.assertEqual(self.events[-2]['purpose'],'id_background_rollback')

    def test_failed_rollback_requires_reload_and_receipt_does_not_retry_mutation(self):
        self.sync.side_effect=ValueError('source no longer available')
        request=self.request();self.owner.handle(request)
        self.assertTrue(self.events[-1]['outcome_unknown']);self.assertTrue(self.events[-1]['requires_reload'])
        self.assertIsNone(self.engine._vram)
        self.owner.handle(request)
        self.assertTrue(self.events[-1]['replayed']);self.review.assert_called_once()

    def test_clear_preserves_reviews_and_source_but_clears_import_bundle(self):
        self.engine._id_background['source']=deepcopy(SOURCE)
        self.engine._id_background['support']['contact']=reviewed('contact')
        self.engine._id_background_bundle={'old':'fixture-only'}
        self.owner.handle(self.request(action='id_clear'))
        self.assertTrue(self.events[-1]['success'])
        self.assertEqual(self.engine._id_background['source'],SOURCE)
        self.assertIsNotNone(self.engine._id_background['support']['contact'])
        self.assertEqual(self.engine._id_background['background']['kind'],'none')
        self.assertIsNone(self.engine._id_background_bundle)

    def test_native_clear_keeps_original_binding_timing_and_direct_semantics(self):
        self.engine._id_background['source']=deepcopy(SOURCE)
        with patch('lumaretouch_engine.creative_derived_source.record',return_value=None), \
             patch.object(M,'bind_source',side_effect=AssertionError('Already bound native clear needs no new bind')):
            self.owner.handle(self.request(action='id_clear'))
        self.assertTrue(self.events[-1]['success'])
        self.assertEqual(self.engine._id_background['source'],SOURCE)

    def test_import_keeps_frozen_bundle_identity_and_rolls_back_both_on_failure(self):
        from lumaretouch_engine import id_background_assets as A
        asset={'path':'/fixture/background.png','sha256':'b'*64,'width':2,'height':2,
               'bits':16,'working_color':'linear-srgb-f32','icc_sha256':None,
               'pixels_sha256':'c'*64,'alpha_sha256':None}
        bundle={'binding':deepcopy(asset),'content':[b'not decoded: transaction fixture only']}
        self.sync.side_effect=[ValueError('asset unavailable during install'),None]
        with patch.object(A,'read',return_value=SimpleNamespace(binding=asset)) as read, \
             patch.object(A,'pack',return_value=bundle):
            self.owner.handle(self.request(action='id_import',path='/fixture/background.png'))
        read.assert_called_once_with('/fixture/background.png')
        self.assertFalse(self.events[-1]['success'])
        self.assertEqual(self.engine._id_background,S.empty())
        self.assertIsNone(self.engine._id_background_bundle)
        self.engine._history_record.assert_not_called()
