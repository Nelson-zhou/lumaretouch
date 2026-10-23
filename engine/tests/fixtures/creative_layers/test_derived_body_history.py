"""AUTHORED / UNRUN: source-switch history isolation, not rendering acceptance.

Synthetic unreferenced support metadata exercises persistence without claiming
measured anatomy, inference, model selection or reviewed operation support.
"""
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import body_pose_document_history as H
from lumaretouch_engine import body_pose_state as B,body_pose_evidence as E
from lumaretouch_engine import shoulder_shape_project as P
from lumaretouch_engine.creative_document_assets import make_asset


def base(value=0.):
    rgba=np.full((4,4,4),value,dtype='<f4');rgba[:,:,3]=1
    return make_asset('rgba',4,4,rgba.tobytes(),original=b'physical original')


def bank(asset,*,support=True,revision=3):
    out=B.empty();out['revision']=revision;out['association_revision']=revision
    out['analysis_runs'][asset]={'detector_limit':1,'limit_reached':False,'census_complete':False}
    if support:
        item={'version':1,'operation_id':'lnx.unimplemented.v1','kind':'synthetic-unreferenced',
              'body_ref':{'asset_sha256':asset,'body_instance_id':'retained-body','analysis_revision':1},
              'points_sha256':'a'*64,'source':{'sha256':asset,'width':4,'height':4,'orientation':E.ORIENTATION},
              'data':{},'data_sha256':E.content_digest({})}
        out['support_assets'][E.content_digest(item)]=item
    return B.check(out)


def frame(value,retained):
    return {'_creative_base':value,'_body_pose_bank':P.pack(retained)}


def test_update_return_keeps_full_original_snapshot_not_append_only_patch():
    original=frame(None,bank('1'*64));returned=frame(base(),B.empty())
    saved=H.decorate(original,returned)
    assert H.KEY not in saved and saved==original
    restored=H.restore(B.empty(),saved,current_state=returned)
    assert restored['support_assets']==bank('1'*64)['support_assets']
    assert restored['revision']>bank('1'*64)['revision']
    redo=H.decorate(returned,frame(None,restored))
    cleared=H.restore(restored,redo,current_state=original)
    assert cleared['support_assets']=={} and cleared['analysis_runs']=={}
    assert cleared['association_revision']>restored['association_revision']


def test_derived_to_derived_switch_never_merges_either_support_bank():
    a,b=base(.1),base(.2)
    first=bank(a['id'][7:]);second=bank(b['id'][7:],revision=7)
    saved=H.decorate(frame(a,first),frame(b,second))
    restored=H.restore(second,saved,current_state=frame(b,second))
    assert restored['support_assets']==first['support_assets']
    assert not set(second['support_assets'])&set(restored['support_assets'])
    assert restored['revision']==8 and restored['association_revision']==8


def test_same_source_sparse_patch_and_monotonic_replay_are_preserved():
    a=base();before=B.empty();after=bank(a['id'][7:],support=False)
    saved=H.decorate(frame(a,before),frame(a,after))
    assert H.KEY in saved
    restored=H.restore(after,saved,current_state=frame(a,after))
    assert restored['analysis_runs']=={} and restored['revision']==after['revision']+1


def test_wrong_or_orphan_source_evidence_is_not_hidden_from_save():
    a=base();wrong=bank('1'*64)
    with pytest.raises(ValueError):H.decorate(frame(a,wrong),frame(a,B.empty()))
    assert H.assets(frame(None,wrong))=={'1'*64}
    orphan=deepcopy(wrong);orphan['analysis_runs']={}
    assert H.assets(frame(None,orphan))=={'1'*64}


def test_source_switch_rejects_sparse_transition_and_requires_current_source():
    a=base();target=frame(a,B.empty());current=frame(None,B.empty())
    with pytest.raises(ValueError):H.restore(B.empty(),target)
    transition=H.decorate(current,current)[H.KEY]
    with pytest.raises(ValueError):H.restore(B.empty(),{**target,H.KEY:transition},current_state=current)


def test_mismatched_dimensions_rejected_even_for_unreferenced_support():
    a=base();owned=bank(a['id'][7:]);item=next(iter(owned['support_assets'].values()))
    item['source']['width']=5;owned['support_assets']={E.content_digest(item):item}
    with pytest.raises(ValueError,match='extent'):H.decorate(frame(a,owned),frame(a,B.empty()))
