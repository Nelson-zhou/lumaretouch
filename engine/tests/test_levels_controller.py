from copy import deepcopy
from dataclasses import replace
from lumaretouch_engine.levels_controller import LevelsController,LevelsPorts
from lumaretouch_engine.ops import levels as L


def fixture():
    events=[];installed=[];rendered=[]
    ports=LevelsPorts(lambda name:None,lambda:'doc-1',lambda spec:installed.append(deepcopy(spec)),
        lambda mode:(rendered.append(mode) or {'event':'frame'}),lambda:{'known':True})
    return LevelsController(ports,events.append),events,installed,rendered


def command():
    spec=L.default_levels();spec['master']['gamma']=2
    return {'action':'set','document_id':'doc-1','spec':spec,'gesture_id':'one','request_id':'r1'}


def test_valid_edit_commits_and_emits_authoritative_receipt():
    c,events,installed,rendered=fixture();p=command();c.handle_command(p)
    assert c.snapshot()['master']['gamma']==2 and rendered==['levels']
    assert events[-1]['success'] and events[-1]['document_id']=='doc-1'
    p['spec']['master']['gamma']=3;assert c.snapshot()['master']['gamma']==2


def test_stale_document_and_malformed_requests_do_not_touch_pipeline():
    for patch in [{'document_id':'old-doc'},{'spec':None},{'gesture_id':'x'*129},{'unknown':1}]:
        c,events,installed,rendered=fixture();p=command();p.update(patch);c.handle_command(p)
        assert installed==[] and rendered==[] and L.is_identity(c.snapshot())
        assert events[-1]['success'] is False and events[-1]['request_id']=='r1'


def test_failed_render_restores_recipe_and_pipeline():
    c,events,installed,rendered=fixture()
    def render(mode):
        rendered.append(mode)
        if mode=='levels':raise RuntimeError('render failed')
        return {'event':'frame'}
    c.ports=replace(c.ports,render_frame=render);c.handle_command(command())
    assert L.is_identity(c.snapshot()) and L.is_identity(installed[-1])
    assert rendered==['levels','levels_rollback'] and not events[-1]['success']


def test_status_failure_also_rolls_back_and_repeated_failures_keep_fresh_ids():
    c,events,installed,_=fixture()
    def fail():raise RuntimeError('status failed')
    c.ports=replace(c.ports,status=fail)
    for request in ['r1','r2']:
        p=command();p['request_id']=request;c.handle_command(p)
    receipts=[e for e in events if e['event']=='levels_result']
    assert [r['request_id'] for r in receipts]==['r1','r2']
    assert all(not r['success'] for r in receipts) and L.is_identity(c.snapshot())
