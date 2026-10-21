"""Protocol startup must not execute the optional tensor runtime."""
import os
import subprocess
import sys


def test_server_and_hello_do_not_import_torch():
    code = '''import sys
from lumaretouch_engine import server
assert 'torch' not in sys.modules
messages=[]
server.emit=messages.append
server.Engine('test-lazy').cmd_hello({})
assert messages[-1]['event']=='ready'
assert 'torch' not in sys.modules
'''
    subprocess.run([sys.executable,'-c',code],check=True,env=os.environ.copy(),timeout=10)


def test_first_tensor_operation_loads_real_runtime():
    code = '''import sys
from lumaretouch_engine.optional_dependencies import optional_module
m=optional_module('torch')
assert 'torch' not in sys.modules
if m is not None:
    assert m.tensor([1,2]).sum().item()==3
    assert 'torch' in sys.modules
'''
    subprocess.run([sys.executable,'-c',code],check=True,env=os.environ.copy(),timeout=30)


def test_missing_dependency_is_none():
    from lumaretouch_engine.optional_dependencies import optional_module
    assert optional_module('lumaretouch_nonexistent_tensor_package') is None
