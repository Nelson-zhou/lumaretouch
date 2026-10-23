"""Authored UNRUN. Local Qoder validation must build native core before execution."""
import copy
import pytest
from lumaretouch_engine import eyelash_state as S,eyelash_project as P
from lumaretouch_engine.eyelash_catalogue import catalogue,CATALOGUE_SHA256


def test_four_parts_fourteen_leaves():
    r=S.neutral()
    assert set(r)=={'version','link_lr','link_ud',*S.PARTS}
    assert len(S.patches(r))==14
    assert len({p['parameter_path'] for p in S.patches(r)})==14
    assert not S.active(r)


def test_fourteen_original_distinct_materials():
    rows=catalogue()
    assert len(rows)==14 and len({r['id'] for r in rows})==14
    assert len({tuple(r[k] for k in ('count','length','curl','width','sweep','variation')) for r in rows})==14
    assert all(len(r['recommended'])>=1 for r in rows)


@pytest.mark.parametrize('part',S.PARTS)
def test_independent_parts(part):
    r={**S.neutral(),'link_lr':False,'link_ud':False}
    changed=S.edit(r,part,{**r[part],'strength':.7})
    assert changed[part]['strength']==.7
    assert all(changed[p]['strength']==0 for p in S.PARTS if p!=part)
    assert r[part]['strength']==0


@pytest.mark.parametrize('lr,ud',[(False,False),(False,True),(True,False),(True,True)])
def test_atomic_lock_components(lr,ud):
    r={**S.neutral(),'link_lr':lr,'link_ud':ud}
    changed=S.edit(r,'left_upper',{**r['left_upper'],'strength':.6})
    expected={'left_upper'}|({'right_upper'} if lr else set())|({'left_lower'} if ud else set())|({'right_lower'} if lr and ud else set())
    assert {p for p in S.PARTS if changed[p]['strength']>0}==expected


def test_partial_linked_recipe_rejected_without_mutating_input():
    r=S.neutral();r['left_upper']['strength']=.8;snapshot=copy.deepcopy(r)
    with pytest.raises(ValueError):S.check(r)
    assert r==snapshot


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,1.1,True,'0.4'])
def test_strength_validation(bad):
    with pytest.raises(ValueError):S.check_eye({**S.neutral_eye(),'strength':bad})


def test_palette_six_and_digest_binding():
    colors=[]
    for c in ('#000000','#111111','#222222','#333333','#444444','#555555'):colors=S.save_colour(colors,c)
    assert len(colors)==6
    with pytest.raises(ValueError):S.save_colour(colors,'#666666')
    assert P.check({'version':1,'catalogue_sha256':CATALOGUE_SHA256,'saved_colours':colors})['saved_colours']==colors
    with pytest.raises(ValueError):P.check({'version':1,'catalogue_sha256':'0'*64,'saved_colours':colors})


def test_rgb_hex_are_strict():
    assert S.colour('#aabbcc')=='#AABBCC'
    assert S.rgb([1,2,255])=='#0102FF'
    for c in ('#abc','red','#GGGGGG'):
        with pytest.raises(ValueError):S.colour(c)


def test_native_zero_and_outside_review():
    import numpy as np
    from lumaretouch_engine.eyelash_native import delta
    source=np.full((12,12,3),.5,dtype=np.float32);support=np.ones((12,12),dtype=np.float32)
    segments=np.array([[2,10,5,2,1,.03]],dtype=np.float32)
    assert np.array_equal(delta(source,support,segments,S.neutral_eye()),np.zeros_like(source))
    support[:,:6]=0
    rendered=delta(source,support,segments,{**S.neutral_eye(),'strength':1})
    assert np.array_equal(rendered[:,:6],np.zeros_like(rendered[:,:6]))
