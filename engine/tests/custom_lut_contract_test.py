"""UNRUN acceptance fixtures. Requires separately built original Rust library."""
import hashlib
import tempfile
import unittest
from pathlib import Path
import numpy as np
from lumaretouch_engine.custom_lut_native import ParsedCube
from lumaretouch_engine.custom_lut_library import Library
from lumaretouch_engine.custom_lut_recipe import make, pack, unpack
from lumaretouch_engine.custom_lut_controller import Controller, render_export

IDENTITY = b'LUT_1D_SIZE 2\n0 0 0\n1 1 1\n'
HDR = b'DOMAIN_MAX 2 2 2\nLUT_1D_SIZE 2\n-1 0 1\n3 4 5\n'

class CustomLutContract(unittest.TestCase):
    def test_numeric_domains_strength_hdr_and_rgb16(self):
        image = np.array([[[1.,1.,1.]]], dtype=np.float64)
        with ParsedCube(HDR) as cube:
            np.testing.assert_array_equal(cube.apply(image, 1), [[[1,2,3]]])
            np.testing.assert_array_equal(cube.apply(image, .5), [[[1,1.5,2]]])
            self.assertIs(cube.apply(image, 0), image)
        image = np.array([[[12345/65535,23456/65535,34567/65535]]], dtype=np.float64)
        with ParsedCube(IDENTITY) as cube:
            np.testing.assert_allclose(cube.apply(image, 1), image, atol=1e-15)

    def test_red_fastest_and_no_cross_channel_1d(self):
        data = b'LUT_3D_SIZE 2\n' + b''.join(f'{b} {r} {g}\n'.encode() for b in range(2) for g in range(2) for r in range(2))
        with ParsedCube(data) as cube:
            np.testing.assert_allclose(cube.apply(np.array([[[.2,.4,.6]]]), 1), [[[.6,.2,.4]]])

    def test_reject_without_partial_output(self):
        for data in [b'LUT_1D_SIZE 2\n0 0 0\nNaN 1 1', IDENTITY+b'1 1 1\n', b'LUT_1D_SIZE 2\nINPUT_MODE foo\n0 0 0\n1 1 1\n', b'LUT_3D_SIZE 66\n', b'LUT_1D_SIZE 2\nDOMAIN_MIN 1 0 0\n0 0 0\n1 1 1\n']:
            with self.assertRaises(ValueError): ParsedCube(data)
        source = np.array([[[0.,0.,float('nan')]]])
        with ParsedCube(IDENTITY) as cube:
            with self.assertRaises(ValueError): cube.apply(source, 1)
            with self.assertRaises(InterruptedError): cube.apply(source, 1, lambda: True)

    def test_immutable_library_portable_remove_recovery(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            x, y = Library(Path(a)), Library(Path(b))
            try:
                ident = x.import_bytes(IDENTITY, '原始名称')
                self.assertEqual(ident, hashlib.sha256(IDENTITY).hexdigest())
                x.rename(ident, '新名称'); x.remove(ident)
                self.assertEqual(x.list(), [])
                self.assertEqual(x.content(ident), IDENTITY)
                x.undo_remove(ident); self.assertEqual(x.list()[0]['name'], '新名称')
                payload = pack(make(ident, .3), x)
                self.assertEqual(unpack(payload, y), make(ident, .3))
                self.assertEqual(y.content(ident), IDENTITY)
                bad = dict(payload['asset'], cube_base64='eA==')
                with self.assertRaises(ValueError): y.restore(bad)
                with self.assertRaises(FileNotFoundError): y.content('0'*64)
                wrong = Path(b)/'wrong.cube'; wrong.write_bytes(HDR)
                before = y.list()
                with self.assertRaises(ValueError): y.recover(ident, wrong)
                self.assertEqual(before, y.list())
            finally: x.close(); y.close()

    def test_cancel_new_document_new_intent_and_commit_failure(self):
        with tempfile.TemporaryDirectory() as d:
            lib = Library(Path(d))
            try:
                ident = lib.import_bytes(IDENTITY, 'test')
                ctl = Controller(lib); ctl.bind('a', 0)
                old = ctl.begin('a', 0); ctl.begin('a', 0)
                image = np.zeros((1,1,3))
                with self.assertRaises(InterruptedError): ctl.prepare_and_commit(old, make(ident), image, lambda *_: self.fail('stale commit'))
                token = ctl.begin('a',0); ctl.bind('b',0)
                with self.assertRaises(InterruptedError): ctl.prepare_and_commit(token, make(ident), image, lambda *_: self.fail('wrong document'))
                token = ctl.begin('b',0)
                def fail(*_): raise RuntimeError('host refused transaction')
                with self.assertRaises(RuntimeError): ctl.prepare_and_commit(token, make(ident), image, fail)
                # Revision unchanged after failed callback; export uses identical math.
                ctl.begin('b',0)
                np.testing.assert_array_equal(render_export(image, make(ident), lib), image)
            finally: lib.close()


class CustomLutIntegratedPersistence(unittest.TestCase):
    def test_project_codec_and_owned_snapshot(self):
        from lumaretouch_engine.custom_lut_asset import CustomCube
        from lumaretouch_engine import project
        from lumaretouch_engine.render_snapshot import own_render_inputs
        cube = CustomCube(IDENTITY, hashlib.sha256(IDENTITY).hexdigest(), 'fixture')
        assets, dropped = {}, []
        encoded = project.encode({'_lut':cube}, assets, dropped, 'recipe')
        self.assertFalse(dropped)
        restored = project.decode(encoded, assets, dropped, 'recipe')['_lut']
        self.assertEqual(restored.content, IDENTITY)
        owned = own_render_inputs({'lut':cube}, max_asset_bytes=1024)
        self.assertEqual(owned.asset_bytes, len(IDENTITY))
        self.assertIs(owned.value['lut'], cube)
        with self.assertRaises(project.ProjectError): project.decode(encoded, {}, [], 'recipe')

    def test_custom_stage_does_not_change_builtin_path(self):
        from lumaretouch_engine.custom_lut_asset import CustomCube
        import torch
        cube=CustomCube(HDR,hashlib.sha256(HDR).hexdigest(),'HDR')
        source=torch.ones((1,3,1,1),dtype=torch.float32)
        result=cube.apply_tensor(source,1.)
        self.assertEqual(result.dtype,source.dtype)
        np.testing.assert_array_equal(result.numpy().reshape(3),[1.,2.,3.])
