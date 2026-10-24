# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Frozen target evidence and explicit replacement policy."""
from copy import deepcopy
import pytest
from lumaretouch_engine import eye_bag_preset_review as R


def wrapper(active=True):
    source={'asset_sha256':'a'*64,'creative_source':None,'original_sha256':'a'*64}
    face={'asset_sha256':'a'*64,'face_instance_id':'face-one','analysis_revision':1}
    image={'mime':'image/png','width':80,'height':60,'sha256':'1'*64}
    coverage={'version':1,'support_transfer':'none','targets':[{'face_ref':face,
        'scope':'target-reviewed-ridge' if active else 'neutral-no-effect',
        'ridge_sha256':'2'*64 if active else None,'sides':['left'] if active else []}]}
    visual={'version':1,'document_id':'doc','revision':'2','source_proof':source,
        **{key:'3'*64 for key in ('before_state_sha256','candidate_state_sha256','before_people_sha256','candidate_people_sha256')},
        'source_size':[80,60],'before_output_size':[80,60],'after_output_size':[80,60],
        'coverage_sha256':R.digest(coverage),'before':image,'after':image}
    owner={'document':{'document_id':'doc','epoch':'workspace','revision':2},
        'people_scope':'project','state_revision':0,'association_revision':0,
        'graph_sha256':'d'*64,'source_proof':source}
    return {'version':1,'preset_sha256':'4'*64,'applies_sha256':'5'*64,'load_id':'load',
        'owner':owner,'face_ref':face,'coverage':coverage,'visual':visual,'replace_legacy':False}


def ack(value):
    v=value['visual']
    return {'document_id':v['document_id'],'revision':v['revision'],
        'before_sha256':v['before']['sha256'],'after_sha256':v['after']['sha256'],
        'coverage_sha256':v['coverage_sha256'],'preset_sha256':value['preset_sha256'],
        'applies_sha256':value['applies_sha256'],'replace_legacy':value['replace_legacy']}


@pytest.mark.parametrize('active',[False,True])
def test_independent_target_side_or_neutral_coverage(active):
    value=wrapper(active);assert R.checked(value)==value
    assert R.acknowledgment(ack(value),value)==ack(value)


@pytest.mark.parametrize('change',['foreign-face','donor-vector','empty-active','wrong-digest','neutral-claims-support'])
def test_scope_and_source_evidence_cannot_be_invented(change):
    value=wrapper(change!='neutral-claims-support');item=value['coverage']['targets'][0]
    if change=='foreign-face':item['face_ref']={**item['face_ref'],'asset_sha256':'f'*64}
    if change=='donor-vector':item['recipe']={'points':[[0,0]]}
    if change=='empty-active':item['sides']=[]
    if change=='wrong-digest':item['ridge_sha256']='broken'
    if change=='neutral-claims-support':item['sides']=['left']
    value['visual']['coverage_sha256']=R.digest(value['coverage'])
    with pytest.raises(ValueError):R.checked(value)


def test_ack_binds_explicit_legacy_choice_and_all_image_identities():
    value=wrapper();wanted=ack(value)
    for key,replacement in [('replace_legacy',True),('replace_legacy',0),('after_sha256','f'*64),('preset_sha256','f'*64)]:
        with pytest.raises(ValueError):R.acknowledgment({**wanted,key:replacement},value)
    with pytest.raises(ValueError):R.acknowledgment({key:item for key,item in wanted.items() if key!='replace_legacy'},value)
