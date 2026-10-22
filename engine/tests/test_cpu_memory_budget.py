import os
import pytest
from lumaretouch_engine.cpu_memory_budget import available_estimate


def fixture(tmp_path):
    proc=tmp_path/'proc';(proc/'self').mkdir(parents=True)
    root=tmp_path/'cgroup';leaf=root/'user'/'app';leaf.mkdir(parents=True)
    (root/'cgroup.controllers').write_text('cpu memory io\n')
    dev=root.stat().st_dev
    (proc/'self/mountinfo').write_text(f'22 1 {os.major(dev)}:{os.minor(dev)} / {root} rw - cgroup2 cgroup rw\n')
    (proc/'self/cgroup').write_text('0::/user/app\n')
    (proc/'meminfo').write_text('MemAvailable: 1000000 kB\n')
    for node,limit,used in ((root/'user',300000000,250000000),(leaf,200000000,100000000)):
        (node/'memory.max').write_text(str(limit));(node/'memory.current').write_text(str(used))
    return proc,root,leaf


def test_actual_leaf_and_all_visible_ancestor_headroom_are_considered(tmp_path):
    proc,root,leaf=fixture(tmp_path)
    assert available_estimate(proc)==50000000
    (root/'user'/'memory.max').write_text('max')
    assert available_estimate(proc)==100000000
    (leaf/'memory.max').write_text('max')
    assert available_estimate(proc)==1024000000


@pytest.mark.parametrize('mode',['hidden','v1','hybrid','subtree','missing','overlaid'])
def test_unknown_or_hidden_limit_never_falls_back_to_host_memory(tmp_path,mode):
    proc,root,leaf=fixture(tmp_path)
    if mode=='hidden':(root/'memory.max').write_text('max')
    elif mode=='v1':(proc/'self/cgroup').write_text('3:memory:/user/app\n')
    elif mode=='hybrid':(proc/'self/cgroup').write_text('0::/user/app\n3:memory:/user/app\n')
    elif mode=='subtree':
        path=proc/'self/mountinfo';path.write_text(path.read_text().replace(' / ', ' /parent ',1))
    elif mode=='missing':(leaf/'memory.current').unlink()
    else:
        path=proc/'self/mountinfo';path.write_text(path.read_text()+f'23 22 1:1 / {leaf} rw - tmpfs tmpfs rw\n')
    with pytest.raises(ValueError):available_estimate(proc)


def test_exhausted_or_invalid_counters_are_not_extra_memory(tmp_path):
    proc,root,leaf=fixture(tmp_path)
    (leaf/'memory.current').write_text('300000000');assert available_estimate(proc)==0
    (leaf/'memory.current').write_text('-1')
    with pytest.raises(ValueError):available_estimate(proc)


@pytest.mark.parametrize('mode',['membership','mount','permission'])
def test_migration_layout_change_or_permission_failure_cannot_return_stale_budget(tmp_path,monkeypatch,mode):
    from pathlib import Path
    proc,root,leaf=fixture(tmp_path);original=Path.open
    def opened(path,*args,**kwargs):
        if path==leaf/'memory.current':
            if mode=='permission':raise PermissionError('denied fixture')
            target=proc/('self/cgroup' if mode=='membership' else 'self/mountinfo')
            with original(target,'a') as handle:handle.write('\n')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opened)
    with pytest.raises(ValueError):available_estimate(proc)
