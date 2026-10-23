"""Authored UNRUN. Execute only in authorized Qoder acceptance environment."""
import unittest
from copy import deepcopy
from lumaretouch_engine import brow_makeup_state as S
from lumaretouch_engine.brow_makeup_catalogue import catalogue
from lumaretouch_engine.brow_makeup_adapters import preset_payload,preset_command

class BrowMakeupContracts(unittest.TestCase):
    def test_neutral_and_fourteen_distinct_noncolour_profiles(self):
        self.assertFalse(S.active(S.neutral()))
        rows=catalogue();self.assertEqual(len(rows),14)
        profiles={(tuple(x['widths']),tuple(x['offsets']),x['density'],x['grain'],x['tilt']) for x in rows}
        self.assertEqual(len(profiles),14)
        self.assertEqual(set(S.PATTERNS),{x['id'] for x in rows})

    def test_independent_sides_and_atomic_relink(self):
        r=S.neutral();r['linked']=False;r['left']['strength']=.6
        self.assertEqual(S.check(r)['right']['strength'],0.)
        invalid=deepcopy(r);invalid['linked']=True
        with self.assertRaises(ValueError):S.check(invalid)
        r['right']=deepcopy(r['left']);r['linked']=True
        self.assertEqual(len(S.patches(r)),7)

    def test_bad_strength_and_unknown_assets(self):
        for value in (True,float('nan'),float('inf'),-.1,1.1):
            r=S.neutral();r['left']['strength']=value
            with self.assertRaises(ValueError):S.check(r)
        r=S.neutral();r['left']['pattern']='copied-pixcake-bitmap'
        with self.assertRaises(ValueError):S.check(r)

    def test_palette_capacity_and_channels(self):
        palette=[]
        for n in range(6):palette=S.save_colour(palette,f'#{n:06X}')
        self.assertEqual(len(S.save_colour(palette,palette[0])),6)
        with self.assertRaises(ValueError):S.save_colour(palette,'#FFFFFF')
        self.assertEqual(S.rgb([255,0,128]),'#FF0080')
        for bad in ([True,0,0],[256,0,0],[0.,0,0]):
            with self.assertRaises(ValueError):S.rgb(bad)
        self.assertEqual(len(S.remove_colour(palette,palette[0])),5)

    def test_preset_contains_no_foreign_support(self):
        payload=preset_payload(S.neutral())
        self.assertEqual(set(payload),{'operation_id','recipe'})
        with self.assertRaises(ValueError):preset_command({},dict(payload,review='foreign'))

# Do not auto-run on import. Synthetic state cases are NOT real-photo visual evidence.
