"""Use fresh child processes; never restrict the pytest parent's environment."""
import json,os,subprocess,sys
import pytest


def run(code):
    result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr+result.stdout
    return json.loads(result.stdout)


def test_native_and_python_socket_calls_are_denied_after_policy():
    got=run('''
import json,socket,errno,ctypes as C
from lumaretouch_engine.privacy import install_offline_policy
status=install_offline_policy()
for family in (socket.AF_INET,socket.AF_INET6):
    try: socket.socket(family,socket.SOCK_STREAM)
    except OSError as e: assert e.errno==errno.EPERM
    else: raise AssertionError('network socket was allowed')
assert install_offline_policy()==status
print(json.dumps(status))
''')
    assert got['enforced'] and got['thread_synchronized'] and got['native_selfcheck']


def test_existing_thread_and_new_child_inherit_denial():
    got=run('''
import threading,socket,errno,json,subprocess,sys
from lumaretouch_engine.privacy import install_offline_policy
start=threading.Event();results=[]
def worker():
    start.wait()
    try: socket.socket()
    except OSError as e: results.append(e.errno)
    else: results.append(0)
t=threading.Thread(target=worker);t.start()
install_offline_policy();start.set();t.join(10)
assert results==[errno.EPERM],results
child=subprocess.run([sys.executable,'-c',"import socket,errno;\\ntry: socket.socket()\\nexcept OSError as e: assert e.errno==errno.EPERM\\nelse: raise AssertionError('allowed')"],capture_output=True,text=True)
assert child.returncode==0,child.stderr
print(json.dumps({'thread':results[0],'child':child.returncode}))
''')
    assert got['child']==0


def test_inherited_socket_descriptors_are_closed():
    import socket
    a,b=socket.socketpair()
    try:
        code='''
import json,os,errno
from lumaretouch_engine.privacy import install_offline_policy
fd=int(os.environ['PROBE_SOCKET_FD']);status=install_offline_policy()
try:os.fstat(fd)
except OSError as e:assert e.errno==errno.EBADF
else:raise AssertionError('inherited socket survived')
print(json.dumps(status))
'''
        result=subprocess.run([sys.executable,'-c',code],pass_fds=[b.fileno()],env={**os.environ,'PROBE_SOCKET_FD':str(b.fileno())},capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
        assert json.loads(result.stdout)['closed_inherited_sockets']>=1
    finally:a.close();b.close()


def test_missing_seccomp_fails_closed(monkeypatch):
    from lumaretouch_engine import privacy
    def fail(*a,**k):raise OSError('missing library')
    monkeypatch.setattr(privacy.C,'CDLL',fail)
    with pytest.raises(privacy.OfflinePolicyError,match='libseccomp2'):
        privacy.install_offline_policy()
    assert not privacy.policy_status()['enforced']


def test_real_engine_entry_reports_enforced_policy():
    result=subprocess.run([sys.executable,'-m','lumaretouch_engine.server','--session','privacy-start'],
                          input='{"cmd":"hello"}\n{"cmd":"shutdown"}\n',capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    ready=next(json.loads(x) for x in result.stdout.splitlines() if json.loads(x).get('event')=='ready')
    assert ready['privacy']['enforced'] and ready['privacy']['native_selfcheck']
    assert not ready['privacy']['network_access']


def test_console_entry_installs_policy_before_server_import():
    from pathlib import Path
    import tomllib,ast
    repo=Path(__file__).parents[2]
    project=tomllib.loads((repo/'engine/pyproject.toml').read_text())
    assert project['project']['scripts']['lumaretouch-engine']=='lumaretouch_engine.bootstrap:main'
    source=(repo/'engine/src/lumaretouch_engine/bootstrap.py').read_text()
    main=next(x for x in ast.parse(source).body if isinstance(x,ast.FunctionDef) and x.name=='main')
    assert isinstance(main.body[0],ast.Expr) and isinstance(main.body[0].value,ast.Call)
    assert main.body[0].value.func.id=='require_offline_or_exit'


def test_real_model_and_export_run_inside_enforced_engine(tmp_path):
    import importlib.util,hashlib
    from pathlib import Path
    if importlib.util.find_spec('torch') is None or importlib.util.find_spec('mediapipe') is None:
        pytest.skip('model runtime unavailable')
    from test_protocol import EngineProcess,_collect_until
    source=Path(__file__).parent/'fixtures/nasa-astronaut-face-crop.png'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    engine=EngineProcess('offline-model-'+str(os.getpid()))
    try:
        engine.send(cmd='hello');ready=engine.wait_for('ready')
        assert ready['privacy']['enforced'] and ready['privacy']['thread_synchronized']
        engine.send(cmd='set_device',device='cpu');engine.wait_for('device_set')
        engine.send(cmd='load_image',path=str(source),strength=0,precompute='mediapipe')
        engine.wait_for('image_ready',timeout=90)
        pc=engine.wait_for('precompute_ready',timeout=90)
        assert pc['mask_nonzero_pixels']['skin']>0
        engine.send(cmd='set_strength',value=.5,channel='skin')
        engine.wait_for('params_set',timeout=30);engine.wait_for('frame',timeout=30)
        engine.send(cmd='export',images=[str(source)],out_dir=str(tmp_path/'out'),format='png')
        done,_=_collect_until(engine,'export_done')
        assert done['failed']==0 and Path(done['images'][0]['out']).is_file(),done
        assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    finally:engine.close()


def test_socket_created_immediately_before_filter_load_is_also_closed():
    """Close inherited descriptors after TSYNC, not before its race window."""
    got = run('''
import json, os, socket, errno, ctypes as C
from lumaretouch_engine import privacy
real_cdll = C.CDLL
seccomp = real_cdll('libseccomp.so.2')
real_load = seccomp.seccomp_load
real_load.argtypes = [C.c_void_p]
real_load.restype = C.c_int
created = []
class Proxy:
    def __getattr__(self, name):
        return getattr(seccomp, name)
proxy = Proxy()
def load_with_last_moment_socket(ctx):
    # No address is supplied and no data is sent. This deterministically models
    # a pre-existing thread creating a socket immediately before TSYNC applies.
    created.append(socket.socket(socket.AF_INET, socket.SOCK_STREAM).detach())
    return real_load(ctx)
proxy.seccomp_load = load_with_last_moment_socket
privacy.C.CDLL = lambda name, *a, **kw: proxy if name == 'libseccomp.so.2' else real_cdll(name, *a, **kw)
status = privacy.install_offline_policy()
try:
    os.fstat(created[0])
except OSError as e:
    assert e.errno == errno.EBADF
else:
    os.close(created[0])
    raise AssertionError('socket opened before filter load escaped descriptor cleanup')
print(json.dumps(status))
''')
    assert got['enforced'] and got['closed_inherited_sockets'] >= 1
