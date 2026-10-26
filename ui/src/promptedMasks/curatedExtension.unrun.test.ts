// AUTHORED, UNRUN: source review only. No test runner, build or typecheck executed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {extensionReady,extensionStatusLabel,downloadProgress,type ModelStatus} from './curatedExtension.ts';
const ready=():ModelStatus=>({running:false,extension_id:'id-background-prompted-v1',result:{state:'installed',installed:true,ready:true,readiness:'cpu-probe-passed',checkpoint_verified:true}});
test('installed alone is never ready',()=>{
  assert.equal(extensionReady({running:false,result:{state:'installed',installed:true}}),false);
  assert.equal(extensionStatusLabel({running:false,result:{state:'installed'}}),'文件已安装 · 尚未准备好');
});
test('requires successful CPU probe and complete verified checkpoint',()=>{
  assert.equal(extensionReady(ready()),true);
  for(const patch of [{installed:false},{ready:false},{readiness:'unchecked'},{checkpoint_verified:false},{state:'invalid'},{state:'unsupported'},{error:'probe failed'}]){
    const value=ready();value.result={...value.result,...patch};assert.equal(extensionReady(value),false);
  }
  assert.equal(extensionReady({...ready(),running:true}),false);
  assert.equal(extensionReady({...ready(),error:'status read failed'}),false);
});
test('never displays invalid download measurements as a successful transfer',()=>{
  for(const [done,total] of [[NaN,100],[101,100],[-1,100],[1,0],[1.2,100],[1,Infinity]])
    assert.equal(downloadProgress({running:true,result:{downloaded_bytes:done,total_bytes:total}}),null);
  assert.deepEqual(downloadProgress({running:true,result:{downloaded_bytes:5,total_bytes:10}}),{done:5,total:10});
});

test('another extension cannot supply SAM readiness',()=>{assert.equal(extensionReady({...ready(),extension_id:'lens-depth-v1'}),false);});
