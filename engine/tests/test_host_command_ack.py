"""The Rust dispatcher must be released even by rejected commands."""
import io
import json
import threading
from unittest.mock import patch
from lumaretouch_engine.server import Engine


def test_ack_is_after_dispatch_and_survives_errors():
    engine=Engine.__new__(Engine)
    engine._quit=False
    engine.stop_flag=threading.Event()
    engine.shm=None
    engine.EDIT_CMDS=()
    calls=[]
    def ok(msg):
        assert '_host_request_id' not in msg
        calls.append(msg['cmd'])
    def fail(msg):
        raise ValueError('expected failure')
    engine._dispatch_table=lambda: {'ok':ok,'fail':fail}
    lines='\n'.join(json.dumps({'cmd':n,'_host_request_id':i})
                    for i,n in enumerate(['ok','fail','unknown','ok'],1))+'\n'
    with patch('sys.stdin',io.StringIO(lines)),patch('sys.stdout',new_callable=io.StringIO) as out:
        engine.run()
    events=[json.loads(line) for line in out.getvalue().splitlines()]
    assert [e['request_id'] for e in events if e['event']=='command_done']==[1,2,3,4]
    assert calls==['ok','ok']
    assert len([e for e in events if e['event']=='error'])==2


def test_plain_protocol_does_not_gain_unsolicited_ack_events():
    engine=Engine.__new__(Engine)
    engine._quit=False;engine.stop_flag=threading.Event();engine.shm=None;engine.EDIT_CMDS=()
    engine._dispatch_table=lambda:{'ok':lambda msg:None}
    with patch('sys.stdin',io.StringIO('{"cmd":"ok"}\n')),patch('sys.stdout',new_callable=io.StringIO) as out:
        engine.run()
    assert out.getvalue()==''
