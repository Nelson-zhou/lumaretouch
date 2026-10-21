import gc
from types import SimpleNamespace
import weakref
import pytest
from lumaretouch_engine.face import MediaPipeFace, _close_mediapipe_graphs


def backend(calls):
    b=MediaPipeFace.__new__(MediaPipeFace)
    b._closed=False
    b._graphs=tuple(SimpleNamespace(close=lambda n=n:calls.append(n)) for n in (1,2))
    b._finalizer=weakref.finalize(b,_close_mediapipe_graphs,b._graphs)
    return b


def test_explicit_close_is_idempotent_and_terminal():
    calls=[]; b=backend(calls)
    b.close();b.close()
    assert calls==[1,2] and b._graphs is None
    with pytest.raises(RuntimeError,match='closed'): b._ensure()


def test_collection_closes_native_resources_without_retaining_owner():
    calls=[]; b=backend(calls);ref=weakref.ref(b)
    del b;gc.collect()
    assert ref() is None and calls==[1,2]


def test_second_graph_closes_even_if_first_close_raises():
    calls=[]
    def bad(): raise RuntimeError('close failed')
    with pytest.raises(RuntimeError,match='close failed'):
        _close_mediapipe_graphs((SimpleNamespace(close=bad),SimpleNamespace(close=lambda:calls.append(2))))
    assert calls==[2]
