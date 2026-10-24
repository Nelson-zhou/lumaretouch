# SPDX-License-Identifier: GPL-3.0-or-later
"""AUTHORED / UNRUN adapter fixtures; mocks are not image/history acceptance."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from lumaretouch_engine.preset_alias_publication import publish


def fixture(name='face_decoration'):
    ack={'review_sha256':'a'*64,'members':[]}
    wrapper={'version':2,'review_sha256':'a'*64,'preset_sha256':'b'*64,'applies_sha256':'c'*64,
        'members':[{'visual':{'document_id':'current','revision':'2'}},{'visual':{'document_id':'sibling','revision':'4'}}]}
    source={'asset_sha256':'d'*64};state={'colour':{'exposure':.2}};before={'colour':{'exposure':0.}}
    ports=SimpleNamespace(status=Mock(return_value={'valid':True}))
    publisher=Mock(return_value=('exact-ledger',{'event':'frame','render_ms':3}))
    setattr(ports,'publish_'+name+'_alias',publisher);setattr(ports,'verify_'+name+'_alias',Mock())
    controller=SimpleNamespace(ports=ports,reviews=object(),_effect_started=False,_scalar_receipt={},
        request_id=lambda p:'original-request',emit=Mock(),last=None)
    store=SimpleNamespace(verify_claimed=Mock())
    family=SimpleNamespace(name=name,ack=name+'_preset_ack',store=store)
    p={'id':'preset','preflight_token':'frozen',family.ack:deepcopy(ack)}
    args=(controller,p,family,{name:wrapper},{'module':{}},{'id':'preset','name':'saved','kind':'custom'},
          object(),('current','/current.png','loaded'),2,before,state,{},['module'],source)
    return args,publisher,store,ack


def test_new_family_passes_exact_ack_and_claimed_pages_without_legacy_override():
    args,publisher,store,ack=fixture()
    with patch('lumaretouch_engine.preset_alias_publication.OA.before_params',return_value={}):
        result=publish(*args)
    options=publisher.call_args.kwargs
    assert options['ack']==ack and options['ack'] is not ack
    options['verify_images']();assert store.verify_claimed.call_count==1
    assert result['batch_id']=='exact-ledger'
    assert result['face_decoration_preset_alias_review']['current_document_id']=='current'
    assert result['alias_members'][1]['result_revision']=='5'
    assert 'eye_bag_preset_alias_review' not in result


def test_existing_eye_family_does_not_receive_new_ack_keyword():
    args,publisher,_,_=fixture('eye_bag')
    with patch('lumaretouch_engine.preset_alias_publication.OA.before_params',return_value={}):publish(*args)
    assert set(publisher.call_args.kwargs)=={'verify_images'}


def test_late_status_failure_retains_known_ledger_and_effect_started():
    args,_,_,_=fixture();controller=args[0]
    controller.ports.status.side_effect=ValueError('late readback')
    with patch('lumaretouch_engine.preset_alias_publication.OA.before_params',return_value={}):
        with pytest.raises(ValueError):publish(*args)
    assert controller._effect_started is True and controller._scalar_receipt['batch_id']=='exact-ledger'
    assert controller._scalar_receipt['face_decoration_preset_alias_review']['member_count']==2


def test_history_readback_source_keeps_unknown_and_checks_expected_undo_state():
    """Authored source contract only; not UI/runtime acceptance."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    source = (root / 'ui/src/people/decorationPresetReadback.ts').read_text()
    assert 'let pending:Readback|null=null' in source
    assert 'result.outcome_unknown===false' in source
    assert "captured.expectedUndone=result.success?captured.action==='undo':captured.action==='redo'" in source
    assert 'row.undone!==captured.expectedUndone' in source
    assert '!terminalAtStart' in source
    assert 'subscribeDecorationPresetAliasWorkspace' in source
    hook = (root / 'ui/src/people/usePeopleWorkflow.ts').read_text()
    assert 'needsRefresh:decorationHistoryReadback()?.terminalKnown===true' in hook
