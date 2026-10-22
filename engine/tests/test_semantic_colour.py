"""Source-only acceptance fixtures. NOT RUN in the implementation session.

Qoder: build packaged Rust core/local mask rasterizer before native tests. No
licensed-photo quality acceptance is inferred from these synthetic contracts.
"""
import unittest
from unittest.mock import patch
import numpy as np
from lumaretouch_engine import semantic_colour_state as S
from lumaretouch_engine import semantic_colour_masks as M
from lumaretouch_engine.semantic_colour_canvas import freeze,validate
from lumaretouch_engine.semantic_colour_stage import SemanticColourStage
from lumaretouch_engine.semantic_colour_analysis import check_receipt,PINNED_SHA,MODEL
from lumaretouch_engine.semantic_colour_capture import geometry_key

class StateContracts(unittest.TestCase):
    def test_old_project_defaults_exact_neutral(self):
        self.assertEqual(S.check(None),S.empty());self.assertFalse(S.active(None))
        a=np.array([[[-0.,-0.5,2.]]],np.float32)
        self.assertIs(SemanticColourStage(None).apply_np(a),a)
    def test_actual_parameter_bounds_and_neutral_curves(self):
        self.assertEqual(len(S.neutral()),50)
        self.assertEqual(S.parameters(S.neutral()),S.neutral())
        for index,bad in ((0,3.),(6,-.1),(26,61.),(27,101.)):
            p=S.neutral();p[index]=bad
            with self.assertRaises(ValueError):S.parameters(p)
    def test_no_fabricated_active_recipe(self):
        p=S.empty();p['enabled']=True
        with self.assertRaises(ValueError):S.check(p)
    def test_neural_receipt_requires_actual_model(self):
        r={'backend':MODEL,'model_sha256':PINNED_SHA,'runtime':'fixture-not-executed',
           'target_input_sha256':'1'*64,'reference_input_sha256':'2'*64,
           'classes':list(S.CLASSES),'analysis_policy':'bounded-rgb8-view-full-float-spatial-samples-v1'}
        self.assertEqual(check_receipt(r),r)
        r['model_sha256']='0'*64
        with self.assertRaises(ValueError):check_receipt(r)

class CanvasMaskContracts(unittest.TestCase):
    def frame(self):
        rgb=np.linspace(0,1,32*48*3,dtype=np.float32).reshape(32,48,3)
        return freeze(rgb,source={'sha256':'0'*64,'width':48,'height':32},geometry_sha256='1'*64,state_key='2'*64,document_id='test',revision='1')
    def test_owned_immutable_render_not_reopened_original(self):
        f=self.frame();self.assertFalse(f.rgb.flags.writeable);self.assertIs(validate(f),f)
        self.assertEqual(f.binding['stage'],S.STAGE)
    def test_float_probabilities_lossless_retained_replay(self):
        a=np.linspace(0,1,32*48,dtype=np.float32).reshape(32,48)
        np.testing.assert_array_equal(M.unpack(M.pack(a)),a)
    def test_domain_mismatch_refused(self):
        f=self.frame();m=M.create('a','a',f.binding,np.zeros((16,16),np.float32));m['domain']='source-normalized'
        with self.assertRaises(ValueError):M.check(m)
    def test_geometry_change_suspends_but_render_colour_change_does_not(self):
        f=self.frame();m=M.create('a','a',f.binding)
        b={**f.binding,'render_sha256':'3'*64};M.assert_geometry(m,b)
        b['geometry_sha256']='4'*64
        with self.assertRaises(ValueError):M.assert_geometry(m,b)
    def test_mask_corruption_rejected_before_use(self):
        p=M.pack(np.ones((16,16),np.float32));p['sha256']='0'*64
        with self.assertRaises(ValueError):M.unpack(p)
    def test_independent_mask_binding_cannot_cross_images(self):
        f=self.frame();m=M.create('a','a',f.binding);b={**f.binding,'source':{**f.binding['source'],'sha256':'8'*64}}
        with self.assertRaises(ValueError):M.assert_geometry(m,b)
    def test_ordinary_colour_edits_do_not_change_geometry_key(self):
        a={'_exposure':[0]*7,'_hsl':[0]*24};b={**a,'_exposure':[1]*7,'_hsl':[4]*24}
        self.assertEqual(geometry_key(a),geometry_key(b))
    def test_new_pixel_material_suspends_while_background_colour_is_editable(self):
        a={'_bg':{'active':True,'matte':np.ones((2,2),np.uint8),'backend':'color_key','tol':.1,'softness':.2,'bg':[0.,0.,0.]}}
        b={'_bg':{**a['_bg'],'bg':[1.,.5,.2]}}
        self.assertEqual(geometry_key(a),geometry_key(b))
        c={'_bg':{**a['_bg'],'matte':np.zeros((2,2),np.uint8)}}
        self.assertNotEqual(geometry_key(a),geometry_key(c))


class AssetContracts(unittest.TestCase):
    def test_applied_masks_are_small_refs_with_deduplicated_readonly_assets(self):
        from lumaretouch_engine import semantic_colour_assets as A
        f=CanvasMaskContracts().frame();plane=np.linspace(0,1,256,dtype=np.float32).reshape(16,16)
        recipe=S.empty();recipe['target']=f.binding
        recipe['masks']=[M.create('a','A',f.binding,plane),M.create('b','B',f.binding,plane)]
        with patch.object(A,'publish'):
            retained,assets=A.retain(recipe)
        self.assertEqual(len(assets),1)
        self.assertFalse(next(iter(assets.values())).flags.writeable)
        for mask in retained['masks']:
            self.assertNotIn('data',mask['base']);self.assertEqual(mask['base']['encoding'],A.ENCODING)
        A.check(retained,assets)
        with self.assertRaises(ValueError):A.check(retained,{})
    def test_project_asset_encoder_deduplicates_repeated_mask_versions(self):
        from lumaretouch_engine import semantic_colour_assets as A,project
        f=CanvasMaskContracts().frame();recipe=S.empty();recipe['target']=f.binding
        recipe['masks']=[M.create('a','A',f.binding,np.ones((16,16),np.float32))]
        with patch.object(A,'publish'):retained,mask_assets=A.retain(recipe)
        state={S.KEY:retained,A.KEY:mask_assets,'_semantic_colour_bundle':None}
        assets={};dropped=[];project.encode([state,state],assets,dropped,'fixture')
        self.assertFalse(dropped);self.assertEqual(len(assets),1)


    def test_encoded_location_wrappers_validate_inactive_resources(self):
        from lumaretouch_engine import semantic_colour_assets as A,semantic_colour_project as P,project
        f=CanvasMaskContracts().frame();recipe=S.empty();recipe['target']=f.binding
        recipe['masks']=[M.create('a','A',f.binding,np.ones((16,16),np.float32))]
        with patch.object(A,'publish'):retained,mask_assets=A.retain(recipe)
        state={S.KEY:retained,A.KEY:mask_assets,P.BUNDLE:None};assets={};dropped=[]
        encoded=project.encode([state,state],assets,dropped,'inactive-fixture')
        self.assertFalse(dropped);P.validate_records(encoded,assets=assets)
        with self.assertRaises(ValueError):P.validate_records(encoded,allowed=False,assets=assets)
        next(iter(assets.values()))['b64']='AA=='
        with self.assertRaises(ValueError):P.validate_records(encoded,assets=assets)


class HostContracts(unittest.TestCase):
    def test_out_of_band_cancel_sets_only_owned_event(self):
        from lumaretouch_engine.semantic_colour_host import SemanticColourHost
        host=SemanticColourHost();one=host.register('one');two=host.register('two')
        self.assertTrue(host.observe_line('{"cmd":"semantic_colour_cancel","request_id":"one"}'))
        self.assertTrue(one.is_set());self.assertFalse(two.is_set())
        self.assertFalse(host.observe_line('{"cmd":"exposure","ev":1}'))
    def test_cancel_before_admission_and_stop_are_retained(self):
        from lumaretouch_engine.semantic_colour_host import SemanticColourHost
        host=SemanticColourHost();host.cancel('late');self.assertTrue(host.register('late').is_set())
        host.stop();self.assertTrue(host.register('after-stop').is_set())
    def test_neutral_project_restore_never_requires_model_or_reference(self):
        from lumaretouch_engine.semantic_colour_project import validate_decoded
        state=validate_decoded({})
        self.assertEqual(state[S.KEY],S.empty());self.assertEqual(state['_semantic_colour_mask_assets'],{})
    def test_project_v12_retains_v11_as_supported_sky_semantic_generation(self):
        from lumaretouch_engine import project
        self.assertEqual(project.SCHEMA,'lrt.project.v12')
        self.assertEqual(project.SEMANTIC_SKY_SCHEMA,'lrt.project.v11')


class NativeContracts(unittest.TestCase):
    def test_zero_mask_preserves_extended_float_bits(self):
        from lumaretouch_engine import semantic_colour_native as N
        a=np.array([[[-0.,-0.5,2.],[.3,.5,.7]]],np.float32)
        p=S.neutral();p[0]=1.
        result=N.apply(a,p,[100,100,100],np.zeros(a.shape[:2],np.float32))
        np.testing.assert_array_equal(result.view(np.uint32),a.view(np.uint32))
    def test_generic_blue_not_orange_gate(self):
        from lumaretouch_engine import semantic_colour_native as N
        a=np.array([[[0.,0.,.4]]],np.float32);p=S.neutral();p[0]=.5
        self.assertGreater(float(N.apply(a,p,[100,100,100])[0,0,2]),.4)
    def test_production_local_group_matches_native_masked_endpoint(self):
        from lumaretouch_engine import semantic_colour_native as N
        f=CanvasMaskContracts().frame();p=S.neutral();p[0]=.7;p[4]=12.
        mask=M.create('local','Local',f.binding,np.ones((16,16),np.float32)*.37)
        recipe=S.empty();recipe.update(enabled=True,local_only=True,target=f.binding,
            reference={'source':f.binding['source'],'render_sha256':f.binding['render_sha256'],'asset_id':'9'*64},
            analysis={'backend':MODEL,'model_sha256':PINNED_SHA,'runtime':'fixture-not-executed',
            'target_input_sha256':'1'*64,'reference_input_sha256':'2'*64,'classes':list(S.CLASSES),
            'analysis_policy':'bounded-rgb8-view-full-float-spatial-samples-v1'},masks=[mask],
            groups=[{'id':'local','name':'Local','enabled':True,'mask_id':'local','baseline':p,'parameters':p}])
        result=SemanticColourStage(recipe,binding=f.binding).apply_np(f.rgb)
        field=M.raster(mask,f.rgb.shape[:2]);expected=N.apply(f.rgb,p,[100,100,100],field)
        np.testing.assert_array_equal(result.view(np.uint32),expected.view(np.uint32))
    def test_tile_mask_continuity_without_materializing_full_planes(self):
        f=CanvasMaskContracts().frame();base=np.linspace(0,1,16*16,dtype=np.float32).reshape(16,16)
        m=M.create('a','a',f.binding,base);t=M.TileMask(m,(64,96))
        try:
            whole=t.tile(0,0,96,64)
            split=np.concatenate((t.tile(0,0,48,64),t.tile(48,0,48,64)),axis=1)
            np.testing.assert_array_equal(whole,split)
        finally:t.close(True)

if __name__=='__main__':unittest.main()
