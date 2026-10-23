"""AUTHORED / UNRUN: immutable fabric recovery ownership, not visual QA."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from test_derived_repair_export import setup
from lumaretouch_engine import creative_derived_global_recovery as G
from lumaretouch_engine import creative_derived_source as D
from lumaretouch_engine import effect_recovery_runtime as R
from lumaretouch_engine import effect_recovery_state as S
from lumaretouch_engine import local_mask_state as M


def recipe(source, *, enabled=True):
    brush={'id':'recover','name':'Recovery','enabled':True,'operation':'add','kind':'brush',
           'opacity':1.,'feather':20.,'points':[[.5,.5]],'axes':[[.1,0.],[0.,.1]]}
    stack=M.empty()['recipe'];stack['objects']=[brush]
    return {'version':1,'source':source,'targets':[{'target':'fabric_fine','enabled':enabled,'recipe':stack}]}


def prepared(monkeypatch):
    spec,pixels=setup();source=D.binding({'creative_base':spec.creative_base})
    spec.effect_recovery=recipe(source)
    monkeypatch.setattr(M,'source_digest',lambda path:'a'*64)
    spec.creative_recovery_context=G.capture({'creative_base':spec.creative_base},spec.effect_recovery,'original')
    spec.effect_recovery_path='original';spec.effect_recovery_stamp=[1,2,3]
    monkeypatch.setattr(M,'file_stamp',lambda path:(1,2,3))
    return spec,pixels,source


def test_disabled_foreign_and_unadapted_global_rows_refuse():
    source={'sha256':'a'*64,'width':4,'height':4};value=recipe(source,enabled=False)
    assert not S.enabled(G.validate(value,source))
    with pytest.raises(ValueError):G.validate(value,{**source,'sha256':'b'*64})
    for name in ('background_replace',):
        bad=deepcopy(value);bad['targets'][0]['target']=name
        with pytest.raises(ValueError):G.validate(bad,source)


def test_snapshot_retains_vectors_and_original_provenance(monkeypatch):
    spec,pixels,source=prepared(monkeypatch)
    snap={'creative_base':spec.creative_base,'effect_recovery':spec.effect_recovery,
          'creative_recovery_context':spec.creative_recovery_context}
    assert G.verify_snapshot(snap,'original',(4,4))==spec.effect_recovery
    assert set(spec.creative_recovery_context)=={'version','source','original_sha256','recipe_sha256'}
    assert spec.creative_recovery_context['original_sha256']!=source['sha256']
    monkeypatch.setattr(M,'source_digest',lambda path:'b'*64)
    with pytest.raises(ValueError):G.verify_snapshot(snap,'original',(4,4))


def test_canonical_float_pixels_and_recipe_are_both_fenced(monkeypatch):
    spec,pixels,_=prepared(monkeypatch)
    with pytest.raises(ValueError):G.verify_pixels(spec,pixels)
    G.stamp_pixels(spec,pixels);G.verify_pixels(spec,pixels)
    changed=pixels.copy();changed[0,0,0]+=.01
    with pytest.raises(ValueError):G.verify_pixels(spec,changed)
    spec.effect_recovery['targets'][0]['enabled']=False
    with pytest.raises(ValueError):G.verify_pixels(spec,pixels)


@pytest.mark.parametrize('bad',[np.nan,-.1,1.1])
def test_no_hdr_or_nonfinite_downconversion(monkeypatch,bad):
    spec,pixels,_=prepared(monkeypatch);pixels[0,0,0]=bad
    with pytest.raises(ValueError):G.stamp_pixels(spec,pixels)


def test_export_rerasterizes_full_resolution_and_preserves_provenance(monkeypatch):
    spec,pixels,source=prepared(monkeypatch);G.stamp_pixels(spec,pixels);seen=[]
    def raster(stack,shape):
        seen.append((deepcopy(stack),shape));return np.full(shape,127,np.uint8)
    monkeypatch.setattr(M.R,'raster',raster)
    R.export_prepare(spec,(4,4),source_pixels=pixels)
    assert seen==[(spec.effect_recovery['targets'][0]['recipe'],(4,4))]
    assert spec.effect_recovery_fields[0]['weight'].dtype==np.uint8
    assert spec.effect_recovery['source']==source
    monkeypatch.setattr(M,'file_stamp',lambda path:(4,5,6))
    with pytest.raises(ValueError):R.export_prepare(spec,(4,4),source_pixels=pixels)


def test_persisted_aliases_and_source_switch_refuse(monkeypatch):
    spec,_,source=prepared(monkeypatch)
    state={'_creative_base':spec.creative_base,'_effect_recovery':spec.effect_recovery}
    G.validate_state(state)
    state['effect_recovery']=S.empty()
    with pytest.raises(ValueError):G.validate_state(state)
    del state['effect_recovery'];state['_effect_recovery']['source']={**source,'sha256':'f'*64}
    with pytest.raises(ValueError):G.validate_state(state)


def test_mutation_requires_adapted_operator_and_actual_pipeline(monkeypatch):
    spec,_,source=prepared(monkeypatch)
    engine=SimpleNamespace(_creative_base=spec.creative_base,_effect_recovery=spec.effect_recovery,
                           _vram=object(),_precompute=object())
    from lumaretouch_engine import creative_derived_repair_runtime as P
    seen=[]
    monkeypatch.setattr(P,'verify_pipeline',lambda pipe,actual:seen.append(actual))
    monkeypatch.setattr(D,'verify_precompute',lambda engine,pc:seen.append('analysis'))
    assert G.mutation_binding(engine,'fabric_fine')==source and seen==[source,'analysis']
    with pytest.raises(ValueError):G.mutation_binding(engine,'skin_smoothing')


def test_empty_recovery_needs_no_export_context_and_retained_rows_survive_off(monkeypatch):
    spec,_,source=prepared(monkeypatch)
    state={'creative_base':spec.creative_base,'fabric_amount':0.,'effect_recovery':spec.effect_recovery}
    assert G.capture(state,S.empty(),'original') is None
    G.validate_state(state)
    context=G.capture(state,spec.effect_recovery,'original')
    assert context['source']==source
    assert G.verify_snapshot({**state,'creative_recovery_context':context},'original',(4,4))==spec.effect_recovery
