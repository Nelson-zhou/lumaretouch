"""AUTHORED / UNRUN: dedicated ID recovery ownership, not runtime acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from lumaretouch_engine import effect_recovery_state as S, local_mask_state as M
from lumaretouch_engine import id_background_state as I, id_background_recovery as R
from lumaretouch_engine import creative_derived_global_recovery as G
from lumaretouch_engine import creative_derived_recovery as REVIEW

SOURCE={'sha256':'a'*64,'width':32,'height':24}


def recovery(enabled=True):
    stack=M.empty()['recipe']
    stack['objects']=[{'id':'recover','name':'Recovery','enabled':True,'operation':'add','kind':'brush',
                      'opacity':1.,'feather':20.,'points':[[.5,.5]],'axes':[[.1,0.],[0.,.1]]}]
    return {'version':1,'source':deepcopy(SOURCE),'targets':[{'target':'id_background','enabled':enabled,'recipe':stack}]}


def test_distinct_target_and_source_bound_vectors():
    value=recovery()
    assert S.target('id_background')!='background_replace'
    assert G.validate(value,SOURCE)==value
    common=deepcopy(value);common['targets'][0]['target']='background_replace'
    assert G.validate(common,SOURCE)==common
    # Admitting common vectors is not permission to reuse an ID or legacy matte
    # consumer. Its independent owner admits only its actual version-2 key.
    from test_common_background_recovery_unrun import snapshot
    from lumaretouch_engine import common_background_recovery as C
    snap=snapshot();assert C.validate_state(snap,snap['effect_recovery'])==snap['effect_recovery']
    snap['_bg'].pop('key_recipe')
    with pytest.raises(ValueError):C.validate_state(snap,snap['effect_recovery'])
    with pytest.raises(ValueError):G.validate(value,{**SOURCE,'sha256':'b'*64})


def test_disabled_retained_source_mismatch_still_refuses():
    recipe=I.empty();recipe['source']={**SOURCE,'sha256':'b'*64}
    with pytest.raises(ValueError):R.validate_state({'id_background':recipe},recovery(False))


def test_disabled_vectors_need_no_export_model_or_fields():
    spec=SimpleNamespace(effect_recovery=recovery(False))
    R.export_prepare(spec);R.verify_export(spec)
    assert spec._id_recovery_consumer is None


def test_original_review_also_requires_id_consumer_evidence(monkeypatch):
    engine=SimpleNamespace(_effect_recovery=recovery())
    consumer={'source':SOURCE,'recipe':{'enabled':True},'fields_sha256':'b'*64}
    monkeypatch.setattr(R,'context',lambda *_args,**_kwargs:deepcopy(consumer))
    proof=REVIEW.global_context(engine,'id_background')
    record={'target':'id_background','people_context':None,'global_context':proof}
    REVIEW.assert_review(engine,record)
    consumer['fields_sha256']='c'*64
    with pytest.raises(ValueError):REVIEW.assert_review(engine,record)


def test_last_row_clear_still_checks_reviewed_consumer(monkeypatch):
    engine=SimpleNamespace(_effect_recovery=S.empty())
    stage=SimpleNamespace(id_recovery_context={'source':SOURCE,'active':True})
    monkeypatch.setattr(R,'context',lambda *_args,**_kwargs:{'source':SOURCE,'active':False})
    with pytest.raises(ValueError):R.assert_consumer(engine,stage)


def test_export_consumer_requires_full_prepared_proof(monkeypatch):
    from lumaretouch_engine import id_background_runtime as runtime
    from lumaretouch_engine import creative_derived_id_background as derived
    recipe=I.empty();recipe['source']=deepcopy(SOURCE)
    spec=SimpleNamespace(effect_recovery=recovery(),id_background=recipe,id_background_bundle=None,
                         id_background_prepared={'test':'initial'})
    monkeypatch.setattr(I,'active',lambda value:True)
    monkeypatch.setattr(runtime,'finish_export',lambda spec:None)
    monkeypatch.setattr(runtime,'_prepared_proof',lambda spec,fields:deepcopy(fields))
    monkeypatch.setattr(derived,'_asset_identity',lambda recipe,bundle:None)
    R.export_prepare(spec);R.verify_export(spec)
    spec.id_background_prepared['test']='changed'
    with pytest.raises(ValueError):R.verify_export(spec)


def test_missing_export_consumer_never_ignores_recovery():
    spec=SimpleNamespace(effect_recovery=recovery())
    with pytest.raises(ValueError):R.verify_export(spec)


def test_original_review_cannot_be_relabelled_face_recovery(monkeypatch):
    engine=SimpleNamespace(_effect_recovery=recovery())
    monkeypatch.setattr(R,'context',lambda *_args,**_kwargs:{'source':SOURCE})
    record={'target':'id_background','people_context':{'face_instance_id':'unrelated'},
            'global_context':REVIEW.global_context(engine,'id_background')}
    with pytest.raises(ValueError):REVIEW.assert_review(engine,record)


def test_simultaneous_compositor_aliases_refuse():
    with pytest.raises(ValueError):R.validate_state({'id_background':I.empty(),'_id_background':I.empty()},recovery(False))
