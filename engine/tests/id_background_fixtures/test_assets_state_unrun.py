"""Authored PC-32475 contracts. UNRUN: local owner must execute and review.

These fixtures do not establish image-quality, runtime or export acceptance.
"""
import copy
import hashlib
import unittest
from lumaretouch_engine import id_background_state as S
from lumaretouch_engine import id_background_assets as A


def binding(content):
    return {'path':'/fixture/background.png','sha256':hashlib.sha256(content).hexdigest(),
            'width':2,'height':2,'bits':8,'working_color':'linear-srgb-f32',
            'icc_sha256':None,'alpha_sha256':None,'pixels_sha256':'0'*64}


class PaletteStateContracts(unittest.TestCase):
    def test_six_unique_colours_and_hex_rgb(self):
        self.assertEqual(S.parse_hex('#aB12EF'),[171,18,239])
        self.assertEqual(len(S.favourites([list(c) for c in S.PRESETS])),6)
        with self.assertRaises(ValueError): S.favourites([[n,n,n] for n in range(7)])
        with self.assertRaises(ValueError): S.favourites([[0,0,0],[0,0,0]])
        with self.assertRaises(ValueError): S.colour([True,0,0])

    def test_stretch_cannot_retain_hidden_position_or_size(self):
        state=S.empty(); state['background'].update(fit='stretch',x=.1)
        with self.assertRaises(ValueError): S.check(state)
        state['background'].update(x=0,scale=2)
        with self.assertRaises(ValueError): S.check(state)

    def test_clear_choice_does_not_delete_source_or_review(self):
        value=S.empty(); value['source']={'sha256':'1'*64,'width':10,'height':20}
        cleared=S.clear_choice(value)
        self.assertEqual(cleared['source'],value['source'])
        self.assertEqual(cleared['support'],value['support'])
        self.assertFalse(cleared['enabled'])
        self.assertIsNone(cleared['background']['color'])
        self.assertEqual(cleared['background']['kind'],'none')

    def test_enabled_without_review_is_rejected(self):
        value=S.empty();value['enabled']=True
        with self.assertRaises(ValueError):S.check(value)

    def test_presets_do_not_copy_another_source_or_asset(self):
        value=S.empty();value['background'].update(kind='asset',asset=binding(b'abc'))
        portable=S.portable(value)
        self.assertTrue(portable['requires_target_asset'])
        self.assertIsNone(portable['background']['asset'])
        self.assertNotIn('support',portable)
        self.assertNotIn('source',portable)
        with self.assertRaises(ValueError):S.apply_portable(S.empty(),portable)
        target=S.empty();other=binding(b'def');target['background']['asset']=other
        self.assertEqual(S.apply_portable(target,portable)['background']['asset'],other)

    def test_nan_unknown_fields_and_bad_modes_rejected(self):
        value=S.empty();value['edge']=float('nan')
        with self.assertRaises(ValueError):S.check(value)
        value=S.empty();value['shadow']['blend']='screen'
        with self.assertRaises(ValueError):S.check(value)
        value=S.empty();value['fake_automatic_contact']=True
        with self.assertRaises(ValueError):S.check(value)


class FrozenAssetContracts(unittest.TestCase):
    def test_bundle_hash_and_chunks(self):
        content=b'not an image: structural check only'
        bundle={'binding':binding(content),'content':[content]}
        self.assertEqual(A.check_bundle(bundle),bundle)
        changed=copy.deepcopy(bundle);changed['content']=[b'changed']
        with self.assertRaises(ValueError):A.check_bundle(changed)
        changed=copy.deepcopy(bundle);changed['content']=[bytearray(content)]
        with self.assertRaises(ValueError):A.check_bundle(changed)

    def test_10mb_boundary_and_project_safe_chunk_size(self):
        content=b'x'*S.MAX_ASSET_BYTES
        chunks=[content[:A.CHUNK],content[A.CHUNK:]]
        self.assertEqual(sum(map(len,A.check_bundle({'binding':binding(content),'content':chunks})['content'])),S.MAX_ASSET_BYTES)
        with self.assertRaises(ValueError):A.check_bundle({'binding':binding(content),'content':[content]})
        content+=b'x'
        with self.assertRaises(ValueError):A.check_bundle({'binding':binding(content),'content':[content[:A.CHUNK],content[A.CHUNK:]]})

    def test_invalid_decoder_bytes_fail_closed(self):
        content=b'not an image'
        with self.assertRaises(Exception):A.unpack({'binding':binding(content),'content':[content]})


class HighBitAndAlphaContracts(unittest.TestCase):
    def test_png16_rgba_retains_low_bits_and_linear_alpha_base(self):
        import tempfile
        import pathlib
        import numpy as np
        import imagecodecs
        rgba=np.array([[[256,257,258,32768],[65535,0,0,0]]],dtype=np.uint16)
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/'rgba16.png';path.write_bytes(imagecodecs.png_encode(rgba))
            value=A.read(str(path))
            self.assertEqual(value.binding['bits'],16)
            self.assertNotEqual(value.pixels[0,0,0],value.pixels[0,0,1])
            self.assertAlmostEqual(float(value.alpha[0,0]),32768/65535,places=6)
            self.assertTrue(np.allclose(A.flatten(value,[255,255,255])[0,1],1))
            self.assertTrue(np.allclose(A.flatten(value,[0,0,0])[0,1],0))
            with self.assertRaises(ValueError):value.pixels.setflags(write=True)
            with self.assertRaises(ValueError):value.alpha.setflags(write=True)
            packed=A.pack(value);path.unlink()
            restored=A.unpack(packed)
            self.assertEqual(restored.binding,value.binding)
            self.assertTrue(np.array_equal(restored.pixels,value.pixels))
            self.assertTrue(np.array_equal(restored.alpha,value.alpha))

    def test_tiff16_unassociated_alpha_and_orientation(self):
        import tempfile
        import pathlib
        import numpy as np
        import tifffile
        rgba=np.array([[[1000,1001,1002,32768],[2000,2001,2002,65535]]],dtype=np.uint16)
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root)/'rgba16.tif'
            tifffile.imwrite(path,rgba,photometric='rgb',extrasamples='unassalpha',extratags=[(274,'H',1,6,False)])
            value=A.read(str(path))
            self.assertEqual((value.binding['height'],value.binding['width']),(2,1))
            self.assertEqual(value.alpha.shape,(2,1))
            self.assertEqual(value.binding['bits'],16)

    def test_icc16_uses_exact_rgb16_conversion(self):
        # Local runtime fixture; no profile or codec downloaded by this test.
        import numpy as np
        from lumaretouch_engine.export import _srgb_bytes
        from lumaretouch_engine.color16 import convert_rgb16
        rgb=np.array([[[1000,1001,1002],[65535,20001,0]]],dtype=np.uint16)
        icc=_srgb_bytes()
        actual=A._colour_manage(rgb,icc)
        self.assertEqual(actual.dtype,np.uint16)
        self.assertTrue(np.array_equal(actual,convert_rgb16(rgb,icc,icc)))


if __name__=='__main__': unittest.main()
