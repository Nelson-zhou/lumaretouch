# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN. Preset transport/planner ownership fixtures, not runtime QA."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from lumaretouch_engine import preset_portrait_review as F
from lumaretouch_engine import eye_bag_preset_store as STORE
from lumaretouch_engine import eye_bag_preserve_scope as EYE
from lumaretouch_engine import collarbone_scope as COLLAR
from lumaretouch_engine.preset_collarbone_lifecycle import CollarbonePresetReplay


def modules(amount=1):
    return {EYE.OP:{'recipe':{'version':2,'amount':amount,'preserve':1.}}}


def test_active_and_explicit_review_selection_do_not_narrow_neutral_reset():
    assert F.select(modules()).name=='eye_bag'
    assert F.select(modules(0)) is None
    assert F.select(modules(0),eye_review=True).name=='eye_bag'
    with pytest.raises(ValueError,match='distinct complete review owners'):
        F.select({**modules(),COLLAR.OP:{}})
    assert F.select({**modules(0),COLLAR.OP:{}}).name=='collarbone'


def test_read_only_preflight_requires_explicit_policy_and_exact_metadata():
    value={'cmd':'preset','action':'preflight','request_id':'read','id':'preset',
        'document_id':'load','module_scope':[EYE.OP],'eye_bag_replace_legacy':False}
    assert STORE.read_only(value)
    assert not STORE.read_only({key:item for key,item in value.items() if key!='eye_bag_replace_legacy'})
    for extra in ('eye_bag_preset_ack','force','preflight_token','path'):
        assert not STORE.read_only({**value,extra:True})
    assert not STORE.read_only({**value,'module_scope':[{}]})
    assert not STORE.read_only({**value,'eye_bag_replace_legacy':0})


def test_image_read_cannot_be_renamed_apply_or_carry_donor_masks():
    value={'cmd':'preset','action':'eye_bag_visual','request_id':'read','id':'preset',
        'document_id':'load','revision':'4','side':'before','sha256':'a'*64,'preflight_token':'token'}
    assert STORE.read_only(value)
    assert not STORE.read_only({**value,'action':'apply'})
    assert not STORE.read_only({**value,'eyes':{'left':{}}})
    assert not STORE.read_only({**value,'side':'support'})


def test_shared_replay_lifecycle_uses_exact_eye_ports_and_keeps_rollback_fence():
    row={'document_id':'document','path':'photo'};calls=[]
    ports=SimpleNamespace(target_row=lambda:row,document_id=lambda:'load',revision=lambda:'5',capture=lambda:{'actual':True},
        eye_bag_replay=lambda *args,**kwargs:calls.append((args,kwargs)) or {},
        verify_eye_bag_applied=lambda *args,**kwargs:calls.append((args,kwargs)))
    owner=CollarbonePresetReplay(ports,row,('document','photo','load'),'5',{'review':'exact'},family='eye_bag')
    with pytest.raises(ValueError): owner.replay({},mode='preset_rollback')
    owner.replay({'candidate':True},mode='preset')
    owner.verify();owner.replay({'previous':True},mode='preset_rollback');owner.verify(rollback=True)
    assert calls[0][1]['strict_local'] is True and calls[2][1]['rollback'] is True
    ports.target_row=lambda:deepcopy(row)
    with pytest.raises(ValueError): owner.replay({},mode='preset_rollback')


def test_controller_keeps_exact_ack_and_reuses_transaction_rollback():
    root=Path(__file__).parents[1]/'src'/'lumaretouch_engine'
    controller=(root/'preset_controller.py').read_text()
    reviews=(root/'local_grade_preset_review.py').read_text()
    assert "portrait.ack:deepcopy(p[portrait.ack])" in controller
    assert 'family=portrait.name' in controller
    assert 'apply_with_rollback(collarbone_transaction.replay' in controller
    assert "portrait.review.acknowledgment" in reviews
    assert 'portrait.store.verify_available(self,token)' in reviews
    assert "eye_bag_replace_legacy" in reviews
    assert 'from .collarbone_visual_store import _Images' in (root/'eye_bag_preset_store.py').read_text()
