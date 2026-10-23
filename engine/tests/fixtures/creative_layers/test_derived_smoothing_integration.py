"""AUTHORED / UNRUN: host scope retention and pipeline transport integration."""
from types import SimpleNamespace
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import creative_smoothing_host as H
from lumaretouch_engine import creative_derived_smoothing as S
from lumaretouch_engine import creative_derived_smoothing_runtime as R
from lumaretouch_engine import server as SERVER
from lumaretouch_engine import export as E
from test_derived_repair_export import setup


def test_missing_scope_never_becomes_whole_image_and_warns_once(monkeypatch):
    pipe=SimpleNamespace(mask_names=[])
    engine=SimpleNamespace(_vram=pipe,_strength=.7,_channel='skin')
    events=[];monkeypatch.setattr(SERVER,'emit',events.append)
    assert H.render_args(engine)==(0.,None)
    assert H.render_args(engine)==(0.,None)
    assert engine._strength==.7 and engine._channel=='skin' and len(events)==1
    assert engine._creative_smoothing_suspended
    pipe.mask_names=['skin']
    monkeypatch.setattr(S,'preview',lambda actual:None)
    assert H.render_args(engine)==(.7,'skin') and engine._creative_smoothing_suspended is None


def test_changed_owned_pixels_refuse_not_suspend_or_broaden(monkeypatch):
    engine=SimpleNamespace(_vram=SimpleNamespace(mask_names=['skin']),_strength=.5,_channel='skin')
    def wrong(_):raise ValueError('foreign actual source')
    monkeypatch.setattr(S,'preview',wrong)
    with pytest.raises(ValueError,match='foreign'):H.render_args(engine)
    assert engine._channel=='skin' and engine._strength==.5


def test_zero_render_needs_no_analysis_and_retains_document_scope():
    pipe=SimpleNamespace(mask_names=[])
    engine=SimpleNamespace(_vram=pipe,_strength=0.,_channel='skin')
    assert H.render_args(engine)==(0.,None) and engine._channel=='skin'
    assert getattr(pipe,'_creative_smoothing_binding',None) is None


def test_proxy_change_preserves_derived_scope_intent(monkeypatch):
    engine=SERVER.Engine.__new__(SERVER.Engine)
    spec,_=setup();state=engine._fresh_doc_state()
    state.update(_creative_base=spec.creative_base,_strength=.7,_channel='skin')
    monkeypatch.setattr(SERVER,'emit',lambda event:None)
    changed=engine._drop_proxy_layers(state,'proxy changed')
    assert changed['_channel']=='skin' and changed['_strength']==.7
    assert state['_channel']=='skin'


def test_semantic_source_reanalysis_is_not_conditioned_on_retained_faces():
    engine=SimpleNamespace(_creative_base=object(),_strength=.5,_channel='skin',_fabric_amount=0.)
    assert H.needs_analysis(engine)
    engine._strength=0.;assert not H.needs_analysis(engine)
    engine._fabric_amount=.3;assert H.needs_analysis(engine)
    engine._creative_base=None;assert not H.needs_analysis(engine)


def test_absent_landmarks_are_empty_not_nan_placeholder():
    carrier=E._MaskCarrier(np.ones((1,4,4),np.float32),None)
    assert carrier.landmarks.shape==(0,3) and carrier.landmarks.dtype==np.float32
