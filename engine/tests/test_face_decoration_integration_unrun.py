# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: scalar routing, neutral, ownership and composition contracts.

No collection, product import execution, tests, build, inference or runtime QA
was performed while authoring. Source wiring checks are not runtime acceptance.
"""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
from types import SimpleNamespace
import numpy as np
import pytest
from lumaretouch_engine import people_state as P, people_algorithms as A, people_effects as E
from lumaretouch_engine import people_resolver as R, face_decoration_state as D
from lumaretouch_engine import face_decoration_scope as S, face_decoration_project as PROJECT
from lumaretouch_engine import people_transfer_adapter as TRANSFER, scope as REGISTRY
from lumaretouch_engine import people_render_plan as PLAN
from test_face_decoration_support_host_unrun import graph,region,ASSET


def test_portable_registry_roundtrip_never_copies_support():
    params={'recipe':{**D.neutral(),'pattern':'mole_pair','strength':.3}}
    assert REGISTRY.check_params(D.OP,params)==params
    assert REGISTRY.MODULES[D.OP]['read'] is S.params_of
    assert REGISTRY.MODULES[D.OP]['write'] is S.install
    assert REGISTRY.MODULES[D.OP]['state_fields']==(S.FIELD,)
    portable={'schema':REGISTRY.PRESET_SCHEMA,'id':'decoration','name':'Decoration',
              'kind':'portrait','modules':{D.OP:params}}
    assert REGISTRY.validate_preset(json.loads(REGISTRY.dump_preset(portable)))['modules']=={D.OP:params}
    for forbidden in ('face_ref','source','reviewed','landmarks','mask','support_assets'):
        with pytest.raises(ValueError):S.check_params({**params,forbidden:{}})
        with pytest.raises(ValueError):S.check_params({'recipe':{**params['recipe'],forbidden:{}}})
    assert D.OP not in REGISTRY.DERIVED_PARAMETER_OPS
    with pytest.raises(REGISTRY.ScopeError):REGISTRY.check_derived_modules({D.OP:params})


def test_neutral_nondefault_pattern_plan_requires_no_analysis_or_support():
    state,ref=graph();face=state['faces'][ref['face_instance_id']]
    face['evidence'].update(status='unresolved',backend='manual_region',detector_model_sha256=None,
                            semantic_model_sha256=None,landmark_digest=None)
    state=P.set_override(state,'face',ref['face_instance_id'],D.OP,'/pattern','mole_pair')
    plan=PLAN.build(state,ASSET,A.defaults(),max_faces=0,per_face_cost=1,total_budget=0,
                    available_evidence={},operation_check=lambda *_:[])
    assert plan['entries'][0]['requires_analysis'] is False and plan['entries'][0]['status']=='ready'
    from lumaretouch_engine.face_decoration_layer import prepare_record
    assert prepare_record(None,None,{**D.neutral(),'pattern':'mole_pair'},None,
                          excluded=None,skin=None,backend=None,semantic_sha=None,reviewed=None) is None
    empty=P.empty();empty=P.set_override(empty,'all_people',ASSET,D.OP,'/pattern','mole_pair')
    assert PROJECT.photograph_dormant(empty,ASSET)
    empty=P.set_override(empty,'all_people',ASSET,D.OP,'/strength',.1)
    assert not PROJECT.photograph_dormant(empty,ASSET)


def test_scalar_transfer_preserves_target_bank_and_each_face_identity():
    from lumaretouch_engine import face_decoration_support as SUPPORT
    source,source_ref=graph();target,target_ref=graph()
    source=P.set_override(source,'face',source_ref['face_instance_id'],D.OP,'/pattern','freckle_bridge')
    source=P.set_override(source,'face',source_ref['face_instance_id'],D.OP,'/strength',.5)
    target,bank=SUPPORT.retain(target,{},target_ref,region());before=deepcopy(target)
    a={'document_id':'source','epoch':'workspace','revision':1};b={'document_id':'target','epoch':'workspace','revision':2}
    payload=TRANSFER.prepare(source,target,source_ref,[target_ref],{D.OP:['/pattern','/strength']},A.defaults(),
                             source_document=a,target_document=b)
    candidate=TRANSFER.candidate(payload,source,target,source_document=a,target_document=b)
    assert candidate['faces']==before['faces'] and set(payload['excluded'])=={'local_assets','landmarks','masks','identity_links'}
    assert all(set(row)=={'operation_id','parameter_path','value'} for row in payload['parameters'])
    assert R.materialize(R.resolve(candidate,target_ref['face_instance_id'],A.defaults()),D.OP,D.neutral(),D.check)['strength']==.5
    SUPPORT.resolve(candidate,bank,target_ref)
    with pytest.raises(ValueError):SUPPORT.resolve(candidate,bank,source_ref)


def test_alias_transition_detects_dormant_override_and_ignores_other_family_faults():
    state,ref=graph();key=ref['face_instance_id']
    zero=P.set_override(state,'face',key,D.OP,'/strength',0.)
    assert PROJECT.changed_assets(state,zero)=={ASSET}
    assert PROJECT.changed_assets(zero,state)=={ASSET}
    unrelated=P.set_override(state,'face',key,A.ENHANCE,'/not-a-real-control',.5)
    assert PROJECT.changed_assets(state,unrelated)==set()
    assert PROJECT.changed_assets(unrelated,P.set_override(unrelated,'face',key,D.OP,'/pattern','mole_pair'))=={ASSET}


def test_decoration_only_recovery_and_vector_gain_do_not_clip_or_change_other_stage():
    state,ref=graph();source=np.full((2,2,3),.1,np.float32)
    delta=np.full_like(source,-.8);delta[:,:,1]=-.4;delta[:,:,2]=-.2
    record=E.LocalEffect(ref,'face_decoration',(0,0,2,2),delta=delta,facts={})
    restored=np.full((2,2),255,np.uint8)
    recovery={(ref['face_instance_id'],'face_decoration'):{'face_ref':ref,'stage':'face_decoration',
        'weight':restored,'content_sha256':sha256(restored.tobytes()).hexdigest(),'recipe_sha256':'f'*64}}
    corrected,facts=E.apply('face_decoration',source,[record])
    assert np.all(corrected>=0) and np.all(corrected<=1)
    applied=corrected-source
    assert np.allclose(applied[:,:,1],applied[:,:,0]*.5,atol=1e-7)
    assert np.allclose(applied[:,:,2],applied[:,:,0]*.25,atol=1e-7)
    assert np.array_equal(E.apply('face_decoration',source,[record],recovery=recovery)[0],source)
    assert np.array_equal(E.apply('blush_makeup',source,[record])[0],source)
    assert facts['composition']=='direction-preserving-per-pixel-SDR-headroom-gain-no-channel-clipping'


def test_source_wiring_original_derived_export_history_presets_and_read_only_contract():
    root=Path(__file__).resolve().parents[1]/'src'/'lumaretouch_engine'
    routes={
      'people_engine_runtime.py':"face_decoration_assets=snapshot.get('support_assets',{})",
      'people_owned_inputs.py':"'face_decoration_assets': support_bank",
      'creative_derived_makeup.py':'face_decoration_support',
      'people_project.py':'validate_decoration_support(value)',
      'workflow_ports.py':'state = capture_decoration(self,state)',
      'scope.py':'FACE_DECORATION.OP:',
      'people_scope.py':'FACE_DECORATION.install(dict(current)',
      'people_host_commands.py':'owner=require_active_owner(engine)',
      'server.py':'if face_decoration_read_only(msg):',
      'people_render_runtime.py':"face_decoration_skin = analysis['face_skin']",
      'people_pipeline.py':"return apply_t(pixels,delta,label='Face decoration')",
      'people_recovery.py':"if target == 'face_decoration':",
      'people_candidate_render.py':'require_transition(engine,row_snapshot(engine,row),candidate,row=row)',
    }
    for name,token in routes.items():assert token in (root/name).read_text(),name
    runtime=(root/'people_render_runtime.py').read_text()
    assert "other_key == key or other['asset_sha256'] != asset_sha256" in runtime
    assert 'face_decoration_excluded[top:bottom,left:right] = 1' in runtime
    stage=(root/'vram.py').read_text()
    assert stage.index("source_effect(self,'blush_makeup',out)") < stage.index("source_effect(self,'face_decoration',out)") < stage.index("source_effect(self,'lipstick',out)")
    assert len((root/'server.py').read_text().splitlines())<=7065
