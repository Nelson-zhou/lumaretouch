"""AUTHORED UNRUN: Qoder/local owner runs after shared integration and Rust packaging."""
import unittest
from copy import deepcopy
import numpy as np
from lumaretouch_engine import extended_tone_state as S
from lumaretouch_engine.extended_tone_controller import ExtendedToneController, Ports
from lumaretouch_engine.extended_tone_project import batch_replace, preset_export, preset_apply
from lumaretouch_engine.extended_tone_native import render

class RecipeCases(unittest.TestCase):
    def test_neutral_and_rejection(self):
        self.assertFalse(S.active(None))
        for value in (True, float('nan'), -101, 101, '1'):
            with self.assertRaises(ValueError): S.check({**S.default(), 'texture': value})
        with self.assertRaises(ValueError): S.check({**S.default(), 'ev': 1})
    def test_monochrome_preserves_saved_vibrance(self):
        s = {**S.default(), 'vibrance': 80}
        self.assertFalse(S.active(s, True)); self.assertEqual(S.check(s)['vibrance'], 80)
    def test_preset_and_batch_lossless(self):
        s = {**S.default(), 'whites': 22, 'texture': -44}
        self.assertEqual(preset_apply({}, preset_export(s))[S.KEY], s)
        original = {'a': {'other': 5}, 'b': {S.KEY: S.default()}}
        result = batch_replace(original, s)
        result['a'][S.KEY]['whites'] = 0
        self.assertEqual(result['b'][S.KEY], s); self.assertNotIn(S.KEY, original['a'])
    def test_dedup_mismatch_stale_doc_and_success(self):
        state = S.default(); count = []; events = []
        def commit(spec):
            nonlocal state
            state=deepcopy(spec); count.append(1); return {'history': {'undo_steps': len(count)}}
        c=ExtendedToneController(Ports(lambda:None, lambda:'doc', lambda:state, lambda:False, commit),events.append)
        r={'cmd':'extended_tone','request_id':'one','document_id':'doc','revision':0,'action':'set','spec':{**state,'brightness':30}}
        self.assertTrue(c.handle(r)['success']); self.assertTrue(c.handle(r)['success']);self.assertEqual(len(count),1)
        self.assertEqual(c.query('one')['phase'],'done')
        with self.assertRaises(ValueError):c.handle({**r,'spec':S.default()})
        self.assertFalse(c.handle({**r,'request_id':'two','document_id':'old'})['success']);self.assertEqual(len(count),1)

class NativeCases(unittest.TestCase):
    def test_float32_neutral_hdr_and_mask(self):
        x=np.array([[[-0.,-1.,3.],[.2,.3,.4]]],np.float32)
        self.assertIs(render(x,S.default()),x)
        y=render(x,{**S.default(),'brightness':50},np.array([[0.,1.]],np.float32))
        np.testing.assert_array_equal(y[0,0].view(np.uint32),x[0,0].view(np.uint32))
        self.assertEqual(y.dtype,np.float32)
    def test_rgb16_retains_sub8bit_values(self):
        x=np.array([[[12001,12002,12003],[40001,40002,40003]]],np.uint16)
        y=render(x,{**S.default(),'brightness':1})
        self.assertEqual(y.dtype,np.uint16)
        self.assertTrue(np.any(y % 257 != 0))
    def test_flat_neutral_texture_clarity_and_vibrance(self):
        x=np.full((17,17,3),.4,np.float32)
        for k in ('texture','clarity','vibrance'):
            for amount in (-100,100):np.testing.assert_allclose(render(x,{**S.default(),k:amount}),x,atol=1e-6,rtol=0)
    def test_locality_detail_does_not_act_as_global_contrast(self):
        x=np.full((65,65,3),.3,np.float32); x[32,32,:]=.35
        y=render(x,{**S.default(),'texture':90})
        np.testing.assert_allclose(y[:10],x[:10],atol=1e-6,rtol=0)
        self.assertTrue(np.any(abs(y[28:37,28:37]-x[28:37,28:37])>1e-6))
    def test_each_control_has_independent_numeric_path(self):
        ramp=np.linspace(.02,.98,51,dtype=np.float32);x=np.repeat(np.tile(ramp,(51,1))[...,None],3,axis=2)
        x[::2,::2]*=.97;x[:,:,0]*=.8
        outputs=[render(x,{**S.default(),k:70}) for k in S.NAMES]
        for i,a in enumerate(outputs):
            self.assertTrue(np.isfinite(a).all());self.assertFalse(np.array_equal(a,x))
            for b in outputs[i+1:]:self.assertFalse(np.array_equal(a,b))
    def test_invalid_mask_and_float64_rejected(self):
        with self.assertRaises(ValueError):render(np.zeros((1,1,3),np.float64),S.default())
        with self.assertRaises(ValueError):render(np.zeros((1,1,3),np.float32),S.default(),np.array([[float('nan')]]))
    def test_small_proxy_detail_bands_do_not_collapse(self):
        x=np.full((19,19,3),.3,np.float32);x[9,9]=.38
        y=render(x,{**S.default(),'texture':100},scale=.25)
        self.assertTrue(np.any(np.abs(y-x)>1e-6))

class SharedIntegrationCases(unittest.TestCase):
    def test_real_monochrome_mode_and_suppression(self):
        from lumaretouch_engine.extended_tone_stage import ExtendedToneStage
        x=np.array([[[.1,.5,.9],[2.,.1,.8]]],np.float32)
        spec={**S.default(),'monochrome':True,'vibrance':100}
        stage=ExtendedToneStage(spec)
        self.assertFalse(stage.active)
        y=stage.finish_np(stage.apply_np(x))
        np.testing.assert_array_equal(y[:,:,0],y[:,:,1]);np.testing.assert_array_equal(y[:,:,1],y[:,:,2])
        self.assertEqual(S.check(spec)['vibrance'],100)
    def test_cancel_native_before_processing(self):
        with self.assertRaises(InterruptedError):render(np.full((9,9,3),.4,np.float32),{**S.default(),'texture':50},cancelled=lambda:True)
    def test_project_schema_gate(self):
        from lumaretouch_engine.extended_tone_project import validate_records
        with self.assertRaises(ValueError):validate_records({S.KEY:S.default()},allowed=False)
        validate_records({S.KEY:S.default()},allowed=True)
    def test_scope_roundtrip(self):
        from lumaretouch_engine.extended_tone_scope import params_of,install
        state={S.KEY:{**S.default(),'clarity':42,'monochrome':True}};out={}
        install(out,params_of(state));self.assertEqual(out,state)
    def test_cancel_ingress_latest_intent(self):
        from lumaretouch_engine.extended_tone_service import Service
        import json
        service=Service()
        service.ingress(json.dumps({'cmd':'extended_tone','request_id':'older'}))
        service.ingress(json.dumps({'cmd':'extended_tone','request_id':'newer'}))
        self.assertTrue(service.events['older'].is_set());self.assertFalse(service.events['newer'].is_set())
        service.ingress(json.dumps({'cmd':'extended_tone_cancel','request_id':'newer'}))
        self.assertTrue(service.events['newer'].is_set())
