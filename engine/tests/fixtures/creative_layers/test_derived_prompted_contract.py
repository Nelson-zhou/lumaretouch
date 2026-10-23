"""AUTHORED / UNRUN: derived prompted transport/cache, no model acceptance."""
from copy import deepcopy
from types import SimpleNamespace
import base64
import io
import json
import numpy as np
from PIL import Image
import pytest
from lumaretouch_engine import creative_derived_prompted as D
from lumaretouch_engine import prompted_mask_resolver as R
from lumaretouch_engine import prompted_mask_source as S
from lumaretouch_engine import prompted_model_manifest as M


def fixture():
    source={'sha256':'a'*64,'width':8,'height':8}
    pixels=np.full((8,8,3),.23456,np.float32);packet=D.from_pixels(source,pixels)
    binding={'prompts':{'points':[{'x':.5,'y':.5,'label':1}],'box':None},'candidate':0,
        'model':{'id':M.MODEL_ID,'checkpoint_sha256':M.CHECKPOINT_SHA256,
                 'config_sha256':M.CONFIG_SHA256,'code_revision':M.SOURCE_REVISION,'contract':S.CONTRACT},
        'input_sha256':packet['descriptor']['input_sha256'],'device':'cpu'}
    obj={'id':'operand','kind':'prompted','enabled':True,'selection':binding}
    out=io.BytesIO();Image.fromarray(np.full((8,8),255,np.uint8)).save(out,format='PNG')
    return source,pixels,packet,binding,obj,base64.b64encode(out.getvalue()).decode()


def test_input_contract_refuses_proxy_hdr_and_wrong_source():
    source,pixels,packet,*_=fixture()
    assert D.validate(packet,source).shape==(8,8,3)
    assert D.cache_identity(packet,source)[1]==source['sha256']
    with pytest.raises(ValueError):D.from_pixels(source,pixels[:4])
    with pytest.raises(ValueError):D.validate(packet,{**source,'sha256':'b'*64})
    bad=pixels.copy();bad[0,0,0]=1.01
    with pytest.raises(ValueError):D.from_pixels(source,bad)
    changed=deepcopy(packet);changed['pixels']=b'\0'+changed['pixels'][1:]
    with pytest.raises(ValueError):D.validate(changed,source)


def test_seed_and_fields_share_immutable_input_identity_without_file(monkeypatch):
    source,pixels,packet,binding,obj,encoded=fixture()
    monkeypatch.setattr(R,'dependency_stamp',lambda:('runtime',))
    R._CACHE.clear()
    from lumaretouch_engine import local_mask_state as LM
    monkeypatch.setattr(LM,'file_stamp',lambda *a:(_ for _ in ()).throw(AssertionError('Original path accessed')))
    R.seed(binding,source,None,encoded,'cpu',source_input=packet)
    result=R.fields({'objects':[obj]},source,None,(16,16),source_input=packet)
    assert result[R.channel(obj)].shape==(16,16) and np.all(result[R.channel(obj)]==1)
    # Full float export has identical model-input identity, never a display proxy.
    replay=R.fields({'objects':[obj]},source,None,(8,8),source_pixels=pixels)
    assert np.all(replay[R.channel(obj)]==1)
    with pytest.raises(ValueError):R.fields({'objects':[obj]},source,'/original.jpg',(8,8),source_input=packet)
    with pytest.raises(ValueError):R.fields({'objects':[obj]},source,None,(8,8),source_input=packet,source_pixels=pixels)


def test_forced_export_recomputes_using_owned_packet_and_checks_result(monkeypatch):
    source,pixels,packet,binding,obj,encoded=fixture();calls=[]
    monkeypatch.setattr(R,'dependency_stamp',lambda:('runtime',));R._CACHE.clear()
    from lumaretouch_engine import prompted_mask_job as J
    result={'source':source,'model':binding['model'],'input_sha256':binding['input_sha256'],
            'inference_size':[8,8],'prompts':binding['prompts'],'_mask_fields':[encoded]*3}
    class Job:
        def __init__(self,path,owned,prompts,device,*,source_input):
            assert path is None and owned==source
            D.validate(source_input,source);calls.append(source_input)
            self.result=deepcopy(result);self.state='ready';self.error=None
        def poll(self):return self.state
        def cancel(self):pass
    monkeypatch.setattr(J,'PromptedJob',Job)
    R.fields({'objects':[obj]},source,None,(8,8),force=True,source_pixels=pixels)
    assert len(calls)==1
    result['source']={**source,'sha256':'b'*64}
    with pytest.raises(ValueError,match='another source'):
        R.fields({'objects':[obj]},source,None,(8,8),force=True,source_pixels=pixels)


def test_worker_uses_hash_verified_bytes_not_original_decode(tmp_path,monkeypatch):
    source,pixels,packet,binding,obj,encoded=fixture()
    from lumaretouch_engine import prompted_mask_worker as W, prompted_model_install as I
    (tmp_path/'source.rgb8').write_bytes(packet['pixels'])
    request={'path':None,'source':source,'device':'cpu','prompts':binding['prompts'],'source_input':packet['descriptor']}
    (tmp_path/'request.json').write_text(json.dumps(request))
    monkeypatch.setattr(S,'decode_source',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Original decoder used')))
    monkeypatch.setattr(I,'installed_runtime_identity',lambda:{'runtime_sha256':'c'*64})
    class Predictor:
        def __init__(self,device):assert device=='cpu'
        def predict(self,image,prompts):
            np.testing.assert_array_equal(image,D.validate(packet,source))
            return {'masks':np.ones((3,8,8),np.uint8),'scores':[.8]*3,'model':binding['model'],
                'input_sha256':binding['input_sha256'],'device':'CPU','inference_size':[8,8]}
    monkeypatch.setattr(S,'Predictor',Predictor)
    W.run(str(tmp_path))
    result=json.loads((tmp_path/'result.json').read_text());D.verify_result(result,source,packet)
    (tmp_path/'source.rgb8').write_bytes(b'bad')
    with pytest.raises(ValueError):W.run(str(tmp_path))


def test_job_admits_only_pathless_owned_transport(tmp_path,monkeypatch):
    source,pixels,packet,*_=fixture()
    from lumaretouch_engine import prompted_mask_job as J,cpu_memory_budget as B
    monkeypatch.setattr(B,'available_estimate',lambda:4*1024**3)
    seen=[]
    class Process:
        def __init__(self,args,**kwargs):
            root=args[args.index('--directory')+1]
            from pathlib import Path
            request=json.loads((Path(root)/'request.json').read_text())
            assert request['path'] is None
            D.validate({'descriptor':request['source_input'],'pixels':(Path(root)/'source.rgb8').read_bytes()},source)
            seen.append(request)
        def poll(self):return 0
    monkeypatch.setattr(J.subprocess,'Popen',Process)
    job=J.PromptedJob(None,source,None,'cpu',source_input=packet);job.cancel()
    assert len(seen)==1
    with pytest.raises(ValueError):J.PromptedJob('/original.jpg',source,None,'cpu',source_input=packet)
