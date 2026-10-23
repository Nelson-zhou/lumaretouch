# SPDX-License-Identifier: GPL-3.0-or-later
"""UNRUN fixtures: local tester must execute after build and shared integration."""
import copy
import numpy as np
import pytest
from lumaretouch_engine import iris_makeup_state as S
from lumaretouch_engine.iris_makeup_geometry import fields
from lumaretouch_engine.iris_makeup_native import delta

def test_catalogue_exact_and_portable():
    assert len(S.PATTERNS)==len(set(S.PATTERNS))==11
    assert S.check(None)==S.neutral()
    for pattern in S.PATTERNS:assert S.check({'version':1,'pattern':pattern,'strength':.6})['pattern']==pattern
    for extra in ('left','right','colour','size','pupil','support'):
        with pytest.raises(ValueError):S.check({**S.neutral(),extra:1})
    for bad in (True,float('nan'),float('inf'),-1,1.1):
        with pytest.raises(ValueError):S.check({**S.neutral(),'strength':bad})

def synthetic_review_fixture():
    # Synthetic unit geometry ONLY. Never real portrait acceptance evidence.
    h,w=96,200;lm=np.zeros((478,3),np.float32);eyes={}
    for side,cx,ids,c,iris in [('right',55,(33,160,158,133,153,144),468,(469,470,471,472)),('left',145,(362,385,387,263,373,380),473,(474,475,476,477))]:
        lid=np.array([[cx-28,48],[cx-12,30],[cx+12,30],[cx+28,48],[cx+12,66],[cx-12,66]],np.float32)
        lm[list(ids),:2]=lid/[w-1,h-1];lm[c,:2]=[cx/(w-1),48/(h-1)]
        lm[list(iris),:2]=np.array([[cx+14,48],[cx,34],[cx-14,48],[cx,62]])/[w-1,h-1]
        def polygon(rx,ry):return [[(cx+rx*np.cos(t))/(w-1),(48+ry*np.sin(t))/(h-1)] for t in np.linspace(0,2*np.pi,32,endpoint=False)]
        eyes[side]={'iris':polygon(13,13),'pupil':polygon(5,5),'highlights':[],'confirmed':True}
    return np.full((h,w,3),.28,np.float32),lm,eyes,np.zeros((h,w),np.float32)

def test_measured_pupil_not_fixed_center():
    src,lm,eyes,veto=synthetic_review_fixture()
    # Offset measured pupil remains protected; no fixed-center circle substitute.
    for p in eyes['right']['pupil']:p[0]+=2/(src.shape[1]-1)
    uv,mask,protected,counts=fields(src,lm,eyes,veto,backend='mediapipe')
    assert np.all(mask[protected]==0) and min(counts.values())>=24
    for pattern in S.PATTERNS:
        out=delta(src,uv,mask,{'version':1,'pattern':pattern,'strength':1})
        assert np.all(out[protected]==0) and np.all(out[mask==0]==0)
        assert np.any(out!=0)

def test_strong_reflection_and_occlusion_reject():
    src,lm,eyes,veto=synthetic_review_fixture();src[:]=.95
    with pytest.raises(ValueError):fields(src,lm,eyes,veto,backend='mediapipe')
    src[:]=.28;veto[:]=1
    with pytest.raises(ValueError):fields(src,lm,eyes,veto,backend='mediapipe')

def test_missing_or_wrong_geometry_reject():
    src,lm,eyes,veto=synthetic_review_fixture()
    with pytest.raises(ValueError):fields(src,lm[:468],eyes,veto,backend='mediapipe')
    with pytest.raises(ValueError):fields(src,lm,eyes,veto,backend='template')
    bad=copy.deepcopy(eyes);bad['right']['pupil']=[[.9,.9],[.95,.9],[.9,.95]]
    with pytest.raises(ValueError):fields(src,lm,bad,veto,backend='mediapipe')

def test_zero_does_not_load_native():
    src=np.full((4,4,3),.3,np.float32);uv=np.zeros((4,4,2),np.float32);mask=np.ones((4,4),np.float32)
    assert np.array_equal(delta(src,uv,mask,S.neutral()),np.zeros_like(src))
