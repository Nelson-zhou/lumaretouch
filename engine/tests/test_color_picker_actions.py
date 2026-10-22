"""Narrow targeted action contracts. No model assets; local execution is not claimed."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from lumaretouch_engine import color_picker_math as M
from lumaretouch_engine.color_picker_controller import ColorPickerController
from lumaretouch_engine.ops import levels as L, curves as C


def request(action='curve'):
    return dict(cmd='color_picker',request_id='r',document_id='1',capture_id='a'*32,ticket='2',generation='3',
                recipe_document_id='b'*32,recipe_revision='4',action=action,channel='master',region={'x':0,'y':0,'width':1,'height':1},delta=0.1)


def engine():
    class E:
        def __init__(self):
            self._load_id='1';self._curves=C.default_curves();self._levels=L.default_levels();self._hsl=(0.,)*24
            self.installed=[];self.frames=[];self.fail=False
            self._vram=SimpleNamespace(set_curves=lambda s:self.installed.append(deepcopy(s)),set_levels=lambda s:self.installed.append(deepcopy(s)),set_hsl=lambda s:self.installed.append(deepcopy(s)))
        def _guard_editable(self,_):return None
        def _write_current_frame(self,mode):
            if self.fail and mode=='color_picker':raise ValueError('render rejected')
            self.frames.append(mode);return {'event':'frame','mode':mode}
        def doc_state(self):return {'document_id':'1','history':{'undo_steps':1,'redo_steps':0}}
    return E()


def prepared(owner,p,recipe):
    proof={k:p[k] for k in ('document_id','capture_id','ticket','generation','recipe_document_id','recipe_revision')}
    owner.capture.prepare_apply=lambda _:dict(**proof,recipe=deepcopy(recipe),sample={'policy':M.POLICY})


def test_prepare_does_not_install_and_terminal_receipt_is_post_history():
    e=engine();events=[];owner=ColorPickerController(e,events.append);p=request()
    recipe=C.default_curves();recipe['master']=[[0.,0.],[0.5,0.6],[1.,1.]];prepared(owner,p,recipe)
    assert owner.prepare(p);assert e.installed==[];assert e._curves==C.default_curves()
    owner.handle(p);assert events[-1]['event']=='frame';assert not any(x['event']=='color_picker_result' for x in events)
    owner.finish(p);result=events[-1]
    assert result['success'] and result['after']==recipe and result['history']=={'undo_steps':1,'redo_steps':0}
    assert owner.prepare(p) is False;owner.finish(p)
    assert events[-1]['replayed'] and len(e.installed)==1


def test_rejected_proof_never_changes_recipe_or_captures_history():
    e=engine();events=[];owner=ColorPickerController(e,events.append);p=request()
    def reject(_):raise ValueError('wrong frozen input')
    owner.capture.prepare_apply=reject
    assert not owner.prepare(p);owner.finish(p)
    assert not events[-1]['success'] and not events[-1]['outcome_unknown'];assert not e.installed


def test_render_failure_restores_old_recipe_and_never_claims_success():
    e=engine();e.fail=True;events=[];owner=ColorPickerController(e,events.append);p=request()
    recipe=C.default_curves();recipe['red']=[[0.,0.1],[1.,1.]];prepared(owner,p,recipe)
    assert owner.prepare(p);owner.handle(p);owner.finish(p)
    assert e._curves==C.default_curves() and e.frames==['color_picker_rollback']
    assert events[-1]['success'] is False and not events[-1]['outcome_unknown']


def test_fresh_duplicate_id_with_changed_action_rejected_before_new_prepare():
    e=engine();events=[];owner=ColorPickerController(e,events.append);p=request();prepared(owner,p,C.default_curves())
    assert owner.prepare(p);owner.handle(p);owner.finish(p)
    p['delta']=0.2;assert not owner.prepare(p);owner.finish(p)
    assert not events[-1]['success'] and not e.installed


def test_scalar_bridge_no_delta_does_not_add_zero_effect_pchip_node(monkeypatch,tmp_path):
    helper=tmp_path/'helper';helper.write_text('not executed')
    monkeypatch.setattr(M,'_helper_path',lambda:helper)
    reply={'version':1,'policy':M.POLICY,'action':'curve','channel':'master','samples':1,
           'mean_srgb':[0.5]*3,'hsl':[0.,0.,0.5],'points':[[0.,0.],[0.5,0.5],[1.,1.]],'point_index':1,'sample_x':0.5,'achieved_delta':0.}
    monkeypatch.setattr(M.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(reply),stderr=''))
    recipe,report=M.calculate([[0.5,0.5,0.5,1.]],'curve','master',0.,C.default_curves())
    assert recipe==C.default_curves() and report['point']==[0.5,0.5]


def test_bridge_rejects_nonfinite_before_helper(monkeypatch):
    monkeypatch.setattr(M,'_helper_path',lambda:pytest.fail('invalid input reached helper'))
    with pytest.raises(ValueError):M.calculate([[float('nan'),0.,0.,1.]],'hsl','master',4.,[0.]*24)
