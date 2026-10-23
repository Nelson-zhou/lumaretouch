"""AUTHORED / UNRUN: immutable replay proof, not native repair acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import creative_derived_repair_runtime as R
from lumaretouch_engine import creative_derived_repairs as S
from lumaretouch_engine import creative_derived_source as D

SOURCE={'sha256':'a'*64,'width':4,'height':4}


def fixture(monkeypatch):
    import torch
    pixels=np.full((4,4,3),127,np.uint8)
    pipe=SimpleNamespace(src_f32=torch.from_numpy(pixels).permute(2,0,1)[None].float()/255.,
        repair_ops=[],redo_ops=[],repair_base=None)
    engine=SimpleNamespace(_vram=pipe,_repair_ops=[],_redo_ops=[])
    monkeypatch.setattr(D,'record',lambda e:{'present':True})
    monkeypatch.setattr(D,'binding',lambda e:deepcopy(SOURCE))
    monkeypatch.setattr(D,'analysis_rgb',lambda e:pixels)
    monkeypatch.setattr(D,'verify',lambda expected,e:expected)
    R.bind(engine)
    return engine,pipe


def test_empty_source_is_bound_without_replayed_bitmap(monkeypatch):
    engine,pipe=fixture(monkeypatch)
    proof=R.verify_pipeline(pipe,SOURCE)
    assert proof['output'] is None and pipe.repair_base is None
    assert proof['stack_sha256']==S.digest_ops([],[],SOURCE)
    proof['source']['sha256']='b'*64
    assert R.verify_pipeline(pipe,SOURCE)['source']==SOURCE


def test_immutable_source_mutation_refuses_before_replay(monkeypatch):
    _,pipe=fixture(monkeypatch);pipe.src_f32+=.01
    with pytest.raises(ValueError):R.prepare_commit(pipe,[],[])
    with pytest.raises(ValueError):R.verify_pipeline(pipe,SOURCE)


def test_output_evidence_binds_actual_float_pixels_and_source():
    pixels=np.full((4,4,3),.25,np.float32);repaired=pixels.copy();repaired[0,0]=.5
    proof=R.make_evidence(SOURCE,pixels,repaired,'b'*64)
    R.verify_evidence(proof,SOURCE,pixels,repaired)
    changed=repaired.copy();changed[0,0]=.6
    with pytest.raises(ValueError):R.verify_evidence(proof,SOURCE,pixels,changed)
    with pytest.raises(ValueError):R.verify_evidence(proof,{**SOURCE,'sha256':'c'*64},pixels,repaired)
    with pytest.raises(ValueError):R.make_evidence(SOURCE,pixels,repaired*3,'b'*64)


def test_forged_repair_buffer_without_commit_refuses(monkeypatch):
    _,pipe=fixture(monkeypatch);pipe.repair_base=pipe.src_f32.clone()+.1
    with pytest.raises(ValueError):R.verify_pipeline(pipe,SOURCE)


def test_rebind_cannot_bless_existing_repair_output(monkeypatch):
    engine,pipe=fixture(monkeypatch);pipe.repair_base=pipe.src_f32.clone()
    with pytest.raises(ValueError,match='freshly loaded'):R.bind(engine)


def test_unbound_pipeline_refuses_derived_operation(monkeypatch):
    _,pipe=fixture(monkeypatch)
    # Keep this fixture focused on ownership independent of vector validation.
    pipe._creative_repair_source=None
    with pytest.raises(ValueError):R.verify_pipeline(pipe,SOURCE)


def test_neutral_replay_proof_committed_only_after_success(monkeypatch):
    _,pipe=fixture(monkeypatch)
    prepared=R.prepare_commit(pipe,[],[])
    original=deepcopy(pipe._creative_repair_evidence)
    invalid=pipe.src_f32.clone();invalid[0,0,0,0]=2
    with pytest.raises(ValueError):R.complete_commit(pipe,prepared,invalid)
    assert pipe._creative_repair_evidence==original
    assert R.complete_commit(pipe,prepared,None)==original
