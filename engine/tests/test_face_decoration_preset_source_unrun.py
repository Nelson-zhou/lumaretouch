# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN: immutable derived admission; not portrait acceptance."""
from copy import deepcopy
import numpy as np
import pytest
from lumaretouch_engine import face_decoration_preset_admission as R, face_decoration_scope as D
from lumaretouch_engine.creative_document_assets import make_asset


def target(colour=.25,alpha=1.):
    pixels=np.full((2,2,4),colour,dtype='<f4'); pixels[:,:,3]=alpha
    base=make_asset('rgba',2,2,pixels.tobytes())
    source={'sha256':base['id'][7:],'width':2,'height':2}
    proof={'asset_sha256':source['sha256'],'creative_source':source,'original_sha256':'a'*64}
    ref={'asset_sha256':source['sha256'],'face_instance_id':'fixture-face','analysis_revision':1}
    owner={'document':{'document_id':'fixture-doc','epoch':'fixture-epoch','revision':2},
        'people_scope':'project','state_revision':3,'association_revision':0,'graph_sha256':'b'*64,'source_proof':proof}
    return {'_creative_base':base,D.FIELD:D.S.neutral(),D.TARGET:ref,D.OWNER:owner,D.REQUESTED:False,
        '_face_decoration_supported':True,'_face_decoration_native_available':True,'_repair_ops':[],
        '_redo_ops':[],'_precompute':None,'_retained_buffer':object()}


def modules():return {D.OP:{'recipe':{**D.S.neutral(),'strength':.3}}}


def test_derived_scalar_only_preserves_exact_target_dependencies():
    before=target(); after=R.candidate(before,modules())
    assert after[D.FIELD]==modules()[D.OP]['recipe'] and after[D.REQUESTED] is True
    for key in before.keys()-{D.FIELD,D.REQUESTED}:assert after[key] is before[key]
    assert R.require_candidate(before,after,modules()) is after
    assert before[D.FIELD]==D.S.neutral()


@pytest.mark.parametrize('colour,alpha',[(1.2,1.),(.25,.5)])
def test_actual_canonical_hdr_alpha_refuse(colour,alpha):
    with pytest.raises(ValueError):R.require_modules(target(colour,alpha),modules())


@pytest.mark.parametrize('field',[D.TARGET,D.OWNER,'_repair_ops','_precompute','_retained_buffer'])
def test_candidate_cannot_replace_target_owned_dependencies(field):
    before=target(); after=R.candidate(before,modules()); after[field]=object()
    with pytest.raises((ValueError,TypeError,AttributeError)):R.require_candidate(before,after,modules())


def test_wrong_actual_source_refuses_even_same_original():
    state=target(); state[D.OWNER]=deepcopy(state[D.OWNER])
    state[D.OWNER]['source_proof']['creative_source']['sha256']='c'*64
    with pytest.raises(ValueError):R.require_modules(state,modules())


def test_generic_derived_scope_not_relaxed():
    state=target()
    with pytest.raises(ValueError):D.install(state,modules()[D.OP])
