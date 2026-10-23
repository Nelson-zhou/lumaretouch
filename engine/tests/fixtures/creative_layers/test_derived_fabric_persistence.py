"""AUTHORED / UNRUN: project ownership, not runtime or photographic acceptance."""
from copy import deepcopy
import pytest
from test_derived_repair_export import setup
from test_derived_global_recovery import recipe
from lumaretouch_engine import project as P, creative_derived_source as D
from lumaretouch_engine import creative_document_project as C


def state():
    spec,_=setup()
    source=D.binding({'creative_base':spec.creative_base})
    return {'_creative_base':spec.creative_base,'_fabric_amount':.5,
            '_effect_recovery':recipe(source,enabled=False)}


def test_existing_project_roundtrip_keeps_only_owned_vectors_and_amount():
    value=state();assets={};dropped=[]
    encoded=P.encode(value,assets,dropped,'state')
    restored=P.decode(encoded,assets,dropped,'state')
    assert not dropped and restored['_effect_recovery']==value['_effect_recovery']
    assert restored['_fabric_amount']==.5
    assert not any('context' in key or 'mask' in key for key in restored)
    assert restored['_creative_base']['id']==value['_creative_base']['id']


@pytest.mark.parametrize('location',['active','inactive','undo','redo'])
def test_every_enclosing_frame_rejects_foreign_disabled_recovery(location):
    value=state();value['_effect_recovery']['source']['sha256']='f'*64
    frame={location:[{'recipe':value}]}
    with pytest.raises(ValueError):C.validate_records(frame)


def test_encoded_foreign_recovery_is_rejected_before_best_effort_decode():
    value=state();assets={};dropped=[]
    encoded=P.encode(value,assets,dropped,'state')
    encoded['_effect_recovery']['source']['width']+=1
    with pytest.raises(P.ProjectError):P.decode(encoded,assets,dropped,'state')
    assert not dropped


def test_unadapted_global_target_cannot_hide_disabled_in_history():
    value=state()
    for target in ('skin_smoothing','background_replace'):
        bad=deepcopy(value);bad['_effect_recovery']['targets'][0]['target']=target
        with pytest.raises(ValueError):C.validate_history_frames([state(),bad])
