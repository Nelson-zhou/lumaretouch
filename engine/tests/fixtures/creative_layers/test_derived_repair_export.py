"""AUTHORED / UNRUN: immutable float repair export contracts, not quality QA."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import export as E
from lumaretouch_engine import creative_derived_repair_export as X
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine.creative_document_assets import make_asset
from lumaretouch_engine.repair_record import RepairOp


def setup():
    rgba=np.zeros((4,4,4),dtype='<f4');rgba[...,3]=1
    base=make_asset('rgba',4,4,rgba.tobytes(),original=b'physical-original-provenance')
    source=D.binding({'creative_base':base})
    recipe={'version':'clone-stamp-v1','points':[[.5,.5]],'offset':[0.,0.],
        'axes':[[.1,0.],[0.,.1]],'hardness':.5,'opacity':1.}
    op=RepairOp(1,np.ones((4,4),np.uint8),recipe,'clone_stamp',source)
    spec=SimpleNamespace(creative_base=base,repair=[op])
    pixels=np.full((4,4,3),.123456,np.float32)
    return spec,pixels


def test_float_replay_requires_canonical_resolver_stamp():
    spec,pixels=setup()
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)
    with pytest.raises(E.ExportError):E.apply_repair_full(pixels,spec.repair,'cpu')
    X.stamp_pixels(spec,pixels);X.verify_pixels(spec,pixels)
    changed=pixels.copy();changed[0,0,0]+=.01
    with pytest.raises(ValueError):X.verify_pixels(spec,changed)


def test_actual_float_divisor_one_and_post_replay_evidence(monkeypatch):
    import torch
    spec,pixels=setup();X.stamp_pixels(spec,pixels);seen=[]
    def replay(cur,ops):
        seen.append(cur.detach().cpu().numpy().copy())
        return cur.clone()+.01,[[0,4,0,4]],1
    monkeypatch.setattr(E,'replay_repair_t',replay)
    out,facts=E.apply_repair_full(pixels,spec.repair,'cpu',spec=spec)
    np.testing.assert_array_equal(seen[0][0].transpose(1,2,0),pixels)
    np.testing.assert_allclose(out,pixels+.01,rtol=0,atol=np.finfo(np.float32).eps)
    assert facts['applied']==1
    assert X.verify_replayed(spec,out) is not None
    out[0,0,0]+=.01
    with pytest.raises(ValueError):X.verify_replayed(spec,out)


def test_mutated_or_foreign_stack_refuses_after_source_resolution():
    spec,pixels=setup();X.stamp_pixels(spec,pixels)
    spec.repair[0].params['opacity']=.2
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)
    spec,pixels=setup();X.stamp_pixels(spec,pixels)
    spec.repair[0].source_binding={**spec.repair[0].source_binding,'sha256':'f'*64}
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)


@pytest.mark.parametrize('bad',[np.nan,-.1,1.1])
def test_hdr_signed_nonfinite_sources_are_not_clipped(bad):
    spec,pixels=setup();pixels[0,0,0]=bad
    with pytest.raises(ValueError):X.stamp_pixels(spec,pixels)


def test_unbound_heal_cannot_be_promoted_to_float_repair():
    spec,pixels=setup()
    spec.repair=[RepairOp(2,np.ones((4,4),np.uint8))]
    with pytest.raises(ValueError):X.stamp_pixels(spec,pixels)


def test_derived_operations_cannot_run_on_integer_original():
    spec,pixels=setup()
    with pytest.raises(E.ExportError):E.apply_repair_full(np.zeros((4,4,3),np.uint16),spec.repair,'cpu')


@pytest.mark.parametrize('dtype,maximum',[(np.uint8,255),(np.uint16,65535)])
def test_original_integer_branch_preserves_its_scale(dtype,maximum):
    pixels=np.full((4,4,3),maximum,dtype=dtype)
    out,_=E.apply_repair_full(pixels,[],'cpu')
    np.testing.assert_array_equal(out,np.ones((4,4,3),np.float32))


def test_canonical_replay_evidence_is_not_exposed_before_replay():
    spec,pixels=setup();X.stamp_pixels(spec,pixels)
    with pytest.raises(ValueError):X.verify_replayed(spec,pixels)
