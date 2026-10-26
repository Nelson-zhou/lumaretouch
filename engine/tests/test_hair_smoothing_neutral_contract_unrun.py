# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN neutral cross-consumer and exact active evidence fixtures.

Synthetic renderer doubles exercise proof admission only. They do not establish
native math, source decode, rendering, UI or photographic acceptance. Authoring
performed static AST/source checks only: no product imports or test execution.
"""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import full_candidate_render as RENDER, people_state as P
from lumaretouch_engine import hair_smoothing_host as HAIR, neck_wrinkle_host as NECK
from lumaretouch_engine import hair_smoothing_state as HS, neck_wrinkle_state as NS
from lumaretouch_engine import original_shadow_transfer_review as SHADOW, spill_transfer_review as SPILL
from lumaretouch_engine import creative_edited_capture_admission as CAPTURE
from lumaretouch_engine.export_recipe import build_export_spec
from test_creative_edited_capture_admission_unrun import snapshot as neutral_snapshot
from test_hair_smoothing_support_unrun import fixture as support_fixture


def identity():
    return {'document_id': 'document', 'revision': '7',
            'source_proof': {'asset_sha256': 'a'*64, 'original_sha256': 'a'*64, 'creative_source': None},
            'candidate_sha256': 'b'*64, 'people_sha256': 'c'*64}


def test_neutral_full_render_proof_preserves_exact_legacy_keyset_and_values():
    proof = identity(); before = deepcopy(proof)
    actual = RENDER._render_proof(proof, (64,64), (64,64), [], [])
    assert actual == {**proof, 'source_size': [64,64], 'output_size': [64,64]}
    assert set(actual) == SHADOW.IDENTITY_FIELDS | {'source_size','output_size'}
    assert proof == before


@pytest.mark.parametrize('family', ['neck_wrinkle', 'hair_smoothing'])
def test_only_actual_nonempty_family_measurements_extend_the_proof(family):
    ref = {'asset_sha256':'a'*64,'face_instance_id':'actual-face','analysis_revision':0}
    rows = [{'face_ref':ref,'measurement_key':'d'*64}]
    result = RENDER._render_proof(identity(),[64,64],[64,64],
        rows if family=='neck_wrinkle' else [], rows if family=='hair_smoothing' else [])
    assert result[family+'_measurements'] == rows
    assert set(result) == set(identity()) | {'source_size','output_size',family+'_measurements'}


@pytest.mark.parametrize('consumer', [SHADOW, SPILL])
def test_unrelated_strict_full_render_consumers_accept_unchanged_neutral_proof(monkeypatch, consumer):
    expected=identity();proof=RENDER._render_proof(expected,[64,64],[64,64],[],[])
    monkeypatch.setattr(RENDER,'render',lambda *args,**kwargs:(np.full((64,64,3),.3,np.float32),proof))
    monkeypatch.setattr(consumer,'_geometry',lambda *args,**kwargs:([64,64],[64,64]))
    compact,display,source,output=consumer._view(None,{}, {},'document','7',expected)
    assert compact['sha256']==display['sha256'] and source==output==[64,64]
    assert compact['width']==compact['height']==64


def render_fixture(monkeypatch, host, operation, *, amount, rows_marker='absent'):
    state,_,ref,_,_,source_packet,_=support_fixture()
    state=P.set_override(state,'face',ref['face_instance_id'],operation,'/amount',amount)
    source=source_packet['source'];proof=RENDER._render_proof(identity(),[64,64],[64,64],[],[])
    family='hair_smoothing' if operation==HS.OP else 'neck_wrinkle'
    if rows_marker!='absent':proof[family+'_measurements']=rows_marker
    monkeypatch.setattr(RENDER,'render',lambda *args,**kwargs:(np.full((64,64,3),.3,np.float32),deepcopy(proof)))
    capture={'row':{},'snapshot':{},'document_id':'document','revision':'7','source':source,
        'identity':identity(),'ref':ref,'context':{'people_graph':state,'people_support_assets':{}}}
    return state,ref,capture,proof


@pytest.mark.parametrize('host,operation',[(HAIR,HS.OP),(NECK,NS.OP)])
def test_own_host_allows_missing_diagnostics_only_for_actual_inactive_graph(monkeypatch,host,operation):
    state,ref,capture,_=render_fixture(monkeypatch,host,operation,amount=0.)
    shown,proof=host._render(None,state,capture)
    assert shown['width']==64 and proof['output_size']==[64,64]
    with pytest.raises(ValueError,match='active renderer omitted'):
        host._render(None,state,capture,measurement_key='d'*64)


@pytest.mark.parametrize('host,operation',[(HAIR,HS.OP),(NECK,NS.OP)])
@pytest.mark.parametrize('rows',['absent',[],None])
def test_active_graph_cannot_blanket_default_missing_empty_or_null_measurements(monkeypatch,host,operation,rows):
    state,ref,capture,_=render_fixture(monkeypatch,host,operation,amount=.4,rows_marker=rows)
    with pytest.raises(ValueError):host._render(None,state,capture)


@pytest.mark.parametrize('host,operation',[(HAIR,HS.OP),(NECK,NS.OP)])
def test_actual_candidate_key_and_exact_active_faces_are_mandatory(monkeypatch,host,operation):
    state,ref,capture,proof=render_fixture(monkeypatch,host,operation,amount=.4)
    family='hair_smoothing' if operation==HS.OP else 'neck_wrinkle'
    proof[family+'_measurements']=[{'face_ref':ref,'measurement_key':'d'*64}]
    # Both proof and state are supplied by the actual render call's frozen graph.
    shown,_=host._render(None,state,capture,candidate=state,assets={},measurement_key='d'*64)
    assert shown['width']==64
    with pytest.raises(ValueError,match='different source/support/algorithm'):
        host._render(None,state,capture,candidate=state,assets={},measurement_key='e'*64)
    proof[family+'_measurements'][0]['face_ref']={**ref,'analysis_revision':ref['analysis_revision']+1}
    with pytest.raises(ValueError,match='measurement owners'):
        host._render(None,state,capture)


@pytest.mark.parametrize('with_people',[False,True])
def test_neutral_export_spec_adds_no_unused_private_repair_fields(with_people):
    value=neutral_snapshot()
    if with_people:
        value['people']={'state':P.empty(),'asset_sha256':'a'*64,'analyses':{},'document_id':'document'}
        value['people_document_id']='document'
    spec,skipped=build_export_spec(value,1200,1600,for_document=True)
    assert skipped==[]
    assert '_neck_wrinkle_repair_inputs' not in vars(spec)
    assert '_hair_smoothing_repair_inputs' not in vars(spec)
    # The general strict data schema remains closed; no broad allowance added.
    CAPTURE._spec_data(spec)
    if not with_people:assert CAPTURE.validate_spec(spec,value).eligible


@pytest.mark.parametrize('operation,field',[(HS.OP,'_hair_smoothing_repair_inputs'),(NS.OP,'_neck_wrinkle_repair_inputs')])
def test_only_needed_family_receives_frozen_private_repair_inputs(operation,field):
    state,_,ref,*_=support_fixture();state=P.set_override(state,'face',ref['face_instance_id'],operation,'/amount',.4)
    value=neutral_snapshot();value['people']={'state':state,'asset_sha256':ref['asset_sha256'],
        'analyses':{},'document_id':'document'};value['people_document_id']='document'
    spec,skipped=build_export_spec(value,1200,1600,for_document=True)
    assert getattr(spec,field)==tuple(value['repair_ops'])
    other='_neck_wrinkle_repair_inputs' if operation==HS.OP else '_hair_smoothing_repair_inputs'
    assert other not in vars(spec)
    assert field not in CAPTURE.SPEC_PRIVATE_FIELDS


@pytest.mark.parametrize('field',['_neck_wrinkle_repair_inputs','_hair_smoothing_repair_inputs'])
def test_creative_edited_capture_schema_was_not_widened_for_unrelated_private_fields(field):
    value=neutral_snapshot();spec,_=build_export_spec(value,1200,1600,for_document=True)
    setattr(spec,field,())
    with pytest.raises(CAPTURE.AdmissionError,match='postbuild ExportSpec'):
        CAPTURE._spec_data(spec)
