"""AUTHORED / UNRUN: vector heal persistence and canonical float boundary."""
from copy import deepcopy
import numpy as np
import pytest
from test_derived_repair_export import setup
from test_derived_heal_vectors import recipe
from lumaretouch_engine import export as E,project as P
from lumaretouch_engine import creative_derived_repair_export as X,creative_derived_repairs as R


def test_heal_export_keeps_float_input_and_owned_recipe(monkeypatch):
    spec,pixels=setup();op=spec.repair[0];op.kind='heal_vector';op.params=recipe()
    seen=[]
    def replay(cur,ops):
        seen.append((cur.detach().cpu().numpy().copy(),deepcopy(ops[0].params)))
        return cur.clone(),[],0
    monkeypatch.setattr(E,'replay_repair_t',replay)
    X.stamp_pixels(spec,pixels)
    out,_=E.apply_repair_full(pixels,spec.repair,'cpu',spec=spec)
    np.testing.assert_array_equal(out,pixels)
    np.testing.assert_array_equal(seen[0][0][0].transpose(1,2,0),pixels)
    assert seen[0][1]==recipe() and X.verify_replayed(spec,out)['source']==op.source_binding
    op.params['reference_size']=[32,32]
    with pytest.raises(ValueError):X.verify_pixels(spec,pixels)


def test_vector_heal_active_and_redo_roundtrip_without_bitmap_output():
    spec,_=setup();op=spec.repair[0];op.kind='heal_vector';op.params=recipe()
    state={'_creative_base':spec.creative_base,'_repair_ops':[],'_redo_ops':[op]}
    assets={};dropped=[];encoded=P.encode(state,assets,dropped,'state')
    restored=P.decode(encoded,assets,dropped,'state')
    assert not dropped and restored['_redo_ops'][0].params==recipe()
    assert R.stack_digest(restored)==R.stack_digest(state)
    assert 'repair_base' not in restored and 'pixels' not in restored['_redo_ops'][0].params
    restored['_redo_ops'][0].source_binding['sha256']='f'*64
    with pytest.raises(ValueError):R.validate_stacks(restored)
