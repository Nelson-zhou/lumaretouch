# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Scalar/ownership fixtures, not photographic acceptance."""
from copy import deepcopy
import pytest
from lumaretouch_engine import eye_bag_preset_admission as D
from lumaretouch_engine import eye_bag_preserve_scope as C, eye_bag_preserve_state as S
from lumaretouch_engine import people_state as P, people_algorithms as A
from lumaretouch_engine import eye_bag_preset_plan as PLAN


def capture():
    asset='a'*64
    ref={'asset_sha256':asset,'face_instance_id':'face-one','analysis_revision':1}
    return {C.FIELD:S.neutral(),C.TARGET:ref,C.REQUESTED:False,
        '_enhance':{'amounts':{'eye_bags':.4,'dark_circles':.3},'built':False},
        C.OWNER:{'document':{'document_id':'target','epoch':'workspace','revision':2},
            'people_scope':'project','state_revision':0,'association_revision':0,'graph_sha256':'d'*64,
            'source_proof':{'asset_sha256':asset,'creative_source':None,'original_sha256':asset}}}


def params(amount=.3):
    return {'recipe':{'version':2,'amount':amount,'preserve':1.}}


def test_generic_active_installer_stays_refused():
    with pytest.raises(ValueError,match='完整前后结果'): C.install(capture(),params())


def test_dedicated_staging_changes_only_requested_scalars_and_explicit_target_legacy():
    before=capture(); sentinel=object();before['runtime_buffer']=sentinel
    out=D.candidate(before,{C.OP:params()},replace_legacy=True)
    assert before['_enhance']['amounts']['eye_bags']==.4
    assert out['_enhance']['amounts']=={'eye_bags':0.,'dark_circles':.3}
    assert out[C.FIELD]==params()['recipe'] and out[C.REQUESTED] is True
    assert out['runtime_buffer'] is sentinel and out[C.TARGET]==before[C.TARGET]
    D.require_candidate(before,out,{C.OP:params()},replace_legacy=True)
    changed=dict(out);changed['runtime_buffer']=object()
    with pytest.raises(ValueError,match='selected scalars only'):
        D.require_candidate(before,changed,{C.OP:params()},replace_legacy=True)


def test_no_replacement_keeps_target_legacy_for_full_planner_conflict_refusal():
    out=D.candidate(capture(),{C.OP:params()},replace_legacy=False)
    assert out['_enhance']['amounts']['eye_bags']==.4


def test_neutral_no_choice_delegates_old_admission_without_new_support(monkeypatch):
    state=capture(); marker=object();calls=[]
    def old(state,modules,**kwargs):calls.append(kwargs);return marker
    monkeypatch.setattr(D.GENERAL,'candidate',old)
    assert D.candidate(state,{C.OP:params(0.)}) is marker
    assert calls==[{'local_replace_legacy':False}]
    C.install_reviewed(state,params(0.),replace_legacy=True)
    assert state['_enhance']['amounts']['eye_bags']==.4


def test_mixed_selected_legacy_is_not_silently_discarded():
    modules={C.OP:params(),A.ENHANCE:{'recipe':{'version':1,'amounts':{'eye_bags':.6}}}}
    for replace in (False,True):
        with pytest.raises(ValueError,match='selects both legacy and v2'):
            D.candidate(capture(),modules,replace_legacy=replace)


def test_target_support_is_not_portable():
    for key in ('eyes','ridge_sha256','recovery','face_ref'):
        with pytest.raises(ValueError):D.candidate(capture(),{C.OP:{**params(),key:{}}})


def test_final_graph_rejects_legacy_conflict_and_preserves_other_people():
    from lumaretouch_engine import people_resolver as R
    state=P.empty();evidence={'backend':'manual_region','detector_model_sha256':None,
        'semantic_model_sha256':None,'landmark_digest':None,'status':'unresolved',
        'source_width':640,'source_height':480,'orientation':'exif_normalized_once'}
    face=P.new_face('a'*64,[.1,.1,.8,.9],evidence,manual=True)
    state['faces'][face['face_instance_id']]=face;ref=P.face_ref(face)
    for op,path,value in ((C.OP,'/amount',.3),(A.ENHANCE,'/eye_bags',.4)):
        state=P.set_override(state,'face',ref['face_instance_id'],op,path,value)
    with pytest.raises(ValueError,match='mutually exclusive'):PLAN.check_graph(state,ref,params()['recipe'])
    state=P.set_override(state,'face',ref['face_instance_id'],A.ENHANCE,'/eye_bags',0.)
    before=deepcopy(state);PLAN.check_graph(state,ref,params()['recipe']);assert state==before


def test_derived_neutral_scalar_needs_owned_source_not_active_analysis(monkeypatch):
    state=capture();base={'id':'retained-source'};binding={'sha256':'a'*64}
    state['_creative_base']=base;state[C.OWNER]['source_proof']['creative_source']=binding
    monkeypatch.setattr(D.SOURCE,'record',lambda value:value.get('_creative_base'))
    monkeypatch.setattr(D.SOURCE,'binding',lambda value:binding)
    monkeypatch.setattr(C,'require_target',lambda value:value[C.TARGET])
    monkeypatch.setattr(C,'owner_identity',lambda value:{'source_proof':value[C.OWNER]['source_proof']})
    def forbidden(*args,**kwargs):raise AssertionError('Neutral reset must not require active analysis')
    monkeypatch.setattr(D.SOURCE,'verify_precompute',forbidden)
    out=D.candidate(state,{C.OP:params(0.)})
    assert out[C.FIELD]['amount']==0 and out['_enhance']['amounts']['eye_bags']==.4
    assert out['_creative_base'] is base


def test_verified_producers_are_recomputed_in_exact_order_not_arbitrary_fields(monkeypatch):
    from lumaretouch_engine import optics_auto_scope as OA, reference_color_scope as RC
    expected={'untouched':'source','_optics':'old'};calls=[]
    optics={'recipe':'verified-optics'};reference={'recipe':'verified-reference'}
    context=D.ProducerContext({'path':'owned.png'},'load','2',optics,reference)
    def optics_verify(record,before,target,row,document,revision,params):
        assert record is optics and target['_optics']=='old';calls.append('optics');return record['recipe']
    def reference_verify(record,before,target,row,document,revision,params):
        assert record is reference and target['_optics']=='verified-optics';calls.append('reference');return record['recipe']
    monkeypatch.setattr(OA,'verify_target',optics_verify)
    monkeypatch.setattr(RC,'verify_target',reference_verify)
    monkeypatch.setattr(RC,'apply_verified',lambda target,recipe:target.update(reference=recipe))
    out=D._producers(dict(expected),{}, {OA.OP:{},RC.OP:{}},context)
    assert calls==['optics','reference'] and out['untouched']=='source'
    assert out['reference']=='verified-reference'
    with pytest.raises(ValueError):D._producers(dict(expected),{}, {},context)
    with pytest.raises(ValueError):D._producers(dict(expected),{}, {OA.OP:{}},{'optics_record':optics})
