"""Authored local acceptance tests. UNRUN; never imported during source work."""
import unittest
from lumaretouch_engine import lipstick_state as S
from lumaretouch_engine.lipstick_catalogue import catalogue
class LipstickContract(unittest.TestCase):
    def test_catalogue_identity(self):
        data=catalogue()
        self.assertEqual(tuple(p['id'] for p in data['patterns']),S.PATTERNS)
        self.assertEqual([p['kernel'] for p in data['patterns']],list(range(13)))
        self.assertEqual(tuple(data['textures']),S.TEXTURES)
    def test_independent_texture_and_colour(self):
        for pattern in S.PATTERNS:
            for texture in S.TEXTURES:
                v={**S.neutral(),'pattern':pattern,'texture':texture,'colour':'#000001','strength':1.}
                self.assertEqual(S.check(v),v)
                self.assertEqual(len(S.patches(v)),4)
    def test_palette_limit_and_duplicates(self):
        palette=[]
        for i in range(6):palette=S.save_colour(palette,f'#{i:06X}')
        self.assertEqual(S.save_colour(palette,'#000001'),palette)
        with self.assertRaises(ValueError):S.save_colour(palette,'#AAAAAA')
        self.assertEqual(len(S.save_colour(S.remove_colour(palette,'#000001'),'#AAAAAA')),6)
    def test_bad_intent(self):
        for patch in ({'strength':float('nan')},{'strength':True},{'strength':1.1},{'texture':'invented'},{'pattern':'apple'},{'colour':'#123'}):
            with self.assertRaises(ValueError):S.check({**S.neutral(),**patch})
