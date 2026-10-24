# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: source contracts, not tested or photographic acceptance.

Boundary doubles copy fixed numeric fixtures, never implement a Python warp or
inverse. Installed-core cases do not build/download or fabricate a native core.
All synthetic coordinates below are isolated numerical examples, never anatomy
supplied as actual evidence to a user operation.
"""
import ctypes as C
from pathlib import Path
from unittest import TestCase, skipUnless
from unittest.mock import patch
import numpy as np

from lumaretouch_engine import torso_length_native as N
from lumaretouch_engine import torso_length_state as S


def synthetic_inputs(amount=1.0):
    pixels = [(550., 520.)] * 33
    actual = {11:(470,650),12:(630,650),13:(440,800),14:(660,800),
              15:(450,1000),16:(650,1000),17:(445,1030),18:(655,1030),
              19:(455,1040),20:(645,1040),21:(450,1020),22:(650,1020),
              23:(480,1150),24:(620,1150)}
    for i, xy in actual.items():
        pixels[i] = xy
    for i in range(25,33):
        pixels[i] = (550.,1350.)
    points = np.array([[x/1200, y/1600, 0., 1., 1.] for x,y in pixels], np.float64)
    support = np.array([10/1200,410/1200,690/1200,1090/1200,10/1600,410/1600,
                        500/1200,430/1600,600/1200,610/1600,
                        420/1200,630/1600,505/1200,1200/1600,
                        595/1200,630/1600,680/1200,1200/1600], np.float64)
    return points, np.array([amount]), support, (1601,1201)


def prepared_fixture(amount=1.0):
    return np.array([10.,410.,690.,1090.,10.,410.,650.,1150.,-40.*amount,1201.,1601.])


class RecordingNative:
    """Fixed private-output constants only; not a mathematical substitute."""
    def __init__(self, status=0, on_enter=None, delta=None, jac=None):
        self.status, self.on_enter = status, on_enter
        self.delta = np.zeros((2,2)) if delta is None else np.array(delta, np.float64)
        self.jac = np.ones(2) if jac is None else np.array(jac, np.float64)
        self.prepared = prepared_fixture()
        self.inputs = []
        self.pointers = []

    @staticmethod
    def _write(pointer, values):
        values = np.ascontiguousarray(values, np.float64)
        C.memmove(pointer, values.ctypes.data, values.nbytes)

    def lrt_torso_length_prepare(self, p, pn, a, an, support, sn, w, h, out, on):
        assert (pn, an, sn, w, h, on) == (165,1,18,1201,1601,11)
        if self.on_enter:
            self.on_enter()
        self.inputs = [np.ctypeslib.as_array(ptr, shape=(length,)).copy()
                       for ptr,length in ((p,pn),(a,an),(support,sn))]
        self.pointers = [C.cast(ptr,C.c_void_p).value for ptr in (p,a,support,out)]
        if not self.status:
            self._write(out,self.prepared)
        return self.status

    def lrt_torso_length_describe(self, state, sn, out, on):
        assert (sn,on) == (11,16)
        # A conservative fixed certificate for the supplied fixed fixture.
        self._write(out,[10,10,1090,1150,410,410,690,650,40,.27,.73,1.27,-40,650,1150,1e-7])
        return self.status

    def lrt_torso_length_evaluate(self, state, sn, p, pn, n, out, on, jac, jn):
        assert sn == 11 and pn == on == 2*n and jn == n
        if self.on_enter:
            self.on_enter()
        self.inputs = [np.ctypeslib.as_array(ptr, shape=(length,)).copy()
                       for ptr,length in ((state,sn),(p,pn))]
        self.pointers = [C.cast(ptr,C.c_void_p).value for ptr in (state,p,out,jac)]
        if not self.status:
            self._write(out,self.delta)
            self._write(jac,self.jac)
        return self.status


class TorsoLengthStateContracts(TestCase):
    def test_exact_identity_signed_amount_and_neutral(self):
        self.assertEqual(S.OPERATION_ID,'lnx.torso_length.v1')
        self.assertEqual(S.CONTROL_ID,'LNX-REF-PC-32473-C-f1662d2dec')
        self.assertEqual(S.REQUIRED_ANCHORS,tuple(range(25)))
        self.assertEqual(S.neutral(),{'version':1,'amount':0.0})
        self.assertEqual(S.LENGTH_GAIN,.08)
        for amount in (-1.,-.125,-0.,0.,.125,1.):
            source={'version':1,'amount':amount}
            result=S.portable(source)
            self.assertIsNot(source,result)
            self.assertEqual(result,source)
            self.assertEqual(S.vector(result),[amount])
            self.assertEqual(S.active(result),amount!=0.)
            self.assertEqual(S.adjust(S.neutral(),'amount',amount),result)

    def test_reject_nonportable_aliases_and_wrong_types_without_coercion(self):
        for amount in (True,np.float64(.2),None,'0.2',float('nan'),float('inf'),-1.01,1.01,10**1000):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                S.check({'version':1,'amount':amount})
        for value in (None,{},[],{'version':True,'amount':0.},
                      {'version':1,'amount':0.,'waist':0.},
                      {'version':1,'amount':0.,'body_ref':'not-portable'}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                S.check(value)
        for key in ('waist','length','overall','width','thigh'):
            with self.assertRaises(ValueError):
                S.adjust(S.neutral(),key,.2)


class TorsoLengthBridgeContracts(TestCase):
    def test_prepare_snapshots_inputs_and_returns_irreversibly_readonly_state(self):
        p,a,s,shape=synthetic_inputs()
        before=[x.copy() for x in (p,a,s)]
        def mutate_originals():
            p.fill(0.); a.fill(0.); s.fill(0.)
        fake=RecordingNative(on_enter=mutate_originals)
        with patch.object(N,'native',return_value=fake):
            state=N.prepare(p,a,s,shape)
        for got,want in zip(fake.inputs,before):
            np.testing.assert_array_equal(got,want.ravel())
        self.assertEqual(len(set(fake.pointers)),4)
        self.assertFalse(state.flags.writeable)
        self.assertIsInstance(state.base,bytes)
        with self.assertRaises(ValueError):
            state.setflags(write=True)
        np.testing.assert_array_equal(state,prepared_fixture())

    def test_describe_reports_conservative_source_facts_only(self):
        with patch.object(N,'native',return_value=RecordingNative()):
            facts=N.facts(prepared_fixture())
        self.assertEqual(facts['support_box'],[10,10,1090,1150])
        self.assertEqual(facts['plateau_box'],[410,410,690,650])
        self.assertEqual(facts['max_displacement'],40)
        self.assertEqual(facts['source_dimensions'],[1201,1601])
        self.assertEqual(facts['head_translation_y'],-40)
        self.assertFalse(facts['runtime_quality_accepted'])

    def test_evaluation_snapshots_and_returns_native_delta_without_python_inverse(self):
        state=prepared_fixture()
        points=np.array([[550.25,500.75],[550.5,900.25]])
        before=[x.copy() for x in (state,points)]
        fake=RecordingNative(on_enter=lambda:(state.fill(0.),points.fill(0.)),
                             delta=[[0.,-40.],[0.,-10.]])
        with patch.object(N,'native',return_value=fake):
            result=N.evaluate(state,points)
        np.testing.assert_array_equal(result,[[0.,-40.],[0.,-10.]])
        for got,want in zip(fake.inputs,before):
            np.testing.assert_array_equal(got,want.ravel())
        self.assertEqual(len(set(fake.pointers)),4)

    def test_shape_and_finite_checks_happen_before_native_entry(self):
        p,a,s,shape=synthetic_inputs()
        with patch.object(N,'native',side_effect=AssertionError('must not load')):
            for args in ((p[:32],a,s,shape),(p,a[:0],s,shape),(p,a,s[:17],shape),
                         (p,a,s,(1601.,1201)),(p,a,s,(True,1201))):
                with self.assertRaises(ValueError):
                    N.prepare(*args)
            for bad in ([1.,2.],[[float('nan'),0.]],np.zeros((2,3))):
                with self.assertRaises(ValueError):
                    N.evaluate(prepared_fixture(),bad)
            with self.assertRaises(ValueError):
                N.facts(np.zeros(10))
        oversized = np.lib.stride_tricks.as_strided(np.zeros((1,2)),
                                                   shape=(N.MAX_POINTS+1,2), strides=(0,8))
        small_state = prepared_fixture()
        with patch.object(N.np,'array',side_effect=AssertionError('must not allocate')):
            # Reject point budget before any point copy. The small state snapshot
            # is intentionally supplied through a fixed already-copied test seam.
            with patch.object(N,'_snapshot',side_effect=lambda value,shape,label:value):
                with self.assertRaises(ValueError):
                    N.evaluate(small_state,oversized)

    def test_native_refusal_and_bad_outputs_never_become_identity(self):
        points=np.array([[550.,500.],[550.,900.]])
        for status in (1,2,4,5,6,8,9,127):
            with patch.object(N,'native',return_value=RecordingNative(status=status)):
                with self.assertRaises(ValueError):
                    N.evaluate(prepared_fixture(),points)
        for fake in (RecordingNative(delta=[[1.,0.],[0.,0.]]),
                     RecordingNative(delta=[[0.,-40.001],[0.,0.]]),
                     RecordingNative(delta=[[0.,float('nan')],[0.,0.]]),
                     RecordingNative(jac=[.5,1.]),RecordingNative(jac=[2.,1.])):
            with patch.object(N,'native',return_value=fake):
                with self.assertRaises(ValueError):
                    N.evaluate(prepared_fixture(),points)

    def test_installed_capability_is_an_abi_check_not_build_or_quality_claim(self):
        for error in (RuntimeError('ABI'),OSError('load'),AttributeError('symbol')):
            with patch.object(N,'native',side_effect=error):
                self.assertFalse(N.available())
        with patch.object(N,'native',return_value=RecordingNative()):
            self.assertTrue(N.available())


@skipUnless((Path(N.__file__).resolve().parent/'bin/liblrt_torso_length.so').is_file(),
            'Already-packaged original Rust core required; no build/download/fallback')
class TorsoLengthInstalledCoreContracts(TestCase):
    def test_actual_endpoint_lengths_head_coherence_and_source_edges(self):
        for amount in (-1.,-.125,0.,.125,1.):
            state=N.prepare(*synthetic_inputs(amount))
            dy=-40.*amount
            # Destination coordinates are known forward images of source anchors.
            source=np.array([[470.,650.],[630.,650.],[480.,1150.],[620.,1150.],
                             [550.,520.],[520.,470.],[580.,570.],[0.,0.],[1200.,1600.]])
            target=source.copy()
            target[[0,1,4,5,6],1]+=dy
            result=N.evaluate(state,target)
            np.testing.assert_allclose(target-result,source,atol=1e-7,rtol=0.)
            self.assertAlmostEqual(target[2,1]-target[0,1],500+40*amount)
            self.assertEqual(N.facts(state)['max_displacement'],abs(dy))

    def test_off_grid_inverse_column_order_and_refusals_both_signs(self):
        for amount in (-1.,1.):
            p,a,s,shape=synthetic_inputs(amount)
            state=N.prepare(p,a,s,shape)
            for x in (215.37,550.37,932.7):
                y=np.linspace(0.,1600.,1001)
                points=np.column_stack((np.full(len(y),x),y))
                source=points-N.evaluate(state,points)
                self.assertTrue(np.all(np.diff(source[:,1])>0))
                self.assertTrue(np.all((source[:,1]>=0)&(source[:,1]<=1600)))
            for index in range(25):
                hidden=p.copy();hidden[index,3]=.79
                with self.assertRaises(ValueError):
                    N.prepare(hidden,a,s,shape)
            narrow=s.copy();narrow[5]=20/1600
            with self.assertRaises(ValueError):
                N.prepare(p,a,narrow,shape)
            edge=s.copy();edge[0]=0.
            with self.assertRaises(ValueError):
                N.prepare(p,a,edge,shape)
            with self.assertRaises(ValueError):
                N.evaluate(state,[[-.001,500.]])
