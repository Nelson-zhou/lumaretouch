import json
from types import SimpleNamespace
import pytest
from lumaretouch_engine import server


def test_dispatch_fence_catches_undo_to_identical_recipe_but_not_state_reads(monkeypatch):
    e=server.Engine.__new__(server.Engine);e._docs=[{'state':{'v':0}}];e._doc_index=0
    monkeypatch.setattr(server,'emit',lambda event:None)
    e._color_capture_controller=lambda:SimpleNamespace(invalidate=lambda:None)
    e._cancel_snapshot=lambda *a:None
    version=e._document_versions().version(e._docs[0])
    table={'history':lambda p:None,'compare':lambda p:None}
    for action in ['undo','redo']:e._process_line(json.dumps({'cmd':'history','action':action}),table)
    assert e._document_versions().version(e._docs[0]).revision==version.revision+2
    e._process_line(json.dumps({'cmd':'history','action':'state'}),table)
    e._process_line(json.dumps({'cmd':'compare'}),table)
    assert e._document_versions().version(e._docs[0]).revision==version.revision+2


def test_explicit_strength_override_fences_before_failed_render(monkeypatch):
    e=server.Engine.__new__(server.Engine);e._docs=[{'state':{}}];e._doc_index=0
    e._vram=None
    e._channel=None;e._grade_scope='all';e._precompute=None;e._params={};e._strength=0
    e._ensure_shm=lambda w,h:object()
    def failed(*a,**kw):raise RuntimeError('fixture render failure')
    e._attach_pipeline=lambda rgb:SimpleNamespace(render=failed)
    e._retouch_render_args=lambda:(e._strength,None)
    v=e._document_versions().version(e._docs[0])
    d=SimpleNamespace(w=2,h=2,rgb=object())
    with pytest.raises(RuntimeError):e._open_session(d,{},t0=1,strength=.4,switched=True)
    assert e._strength==.4 and e._document_versions().version(e._docs[0]).revision>v.revision
