// AUTHORED / UNRUN. Readiness presentation fixtures, not native/model acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handModelReady} from './handModelSetup.ts';
import type {ModelStatus} from '../promptedMasks/curatedExtension';
const ready=():ModelStatus=>({extension_id:'hand-landmarker-v1',running:false,result:{state:'installed',installed:true,ready:true,checkpoint_verified:true,readiness:'cpu-probe-passed'}});
test('requires native hand identity and all readiness evidence (UNRUN)',()=>{
  assert.equal(handModelReady(ready()),true);
  assert.equal(handModelReady(null),false);
  for(const patch of [{running:true},{extension_id:'id-background-prompted-v1'},{error:'failed'}])
   assert.equal(handModelReady({...ready(),...patch}),false);
  for(const patch of [{state:'not-installed'},{installed:false},{ready:false},{checkpoint_verified:false},{readiness:'unchecked'},{error:'stale'}]){
   const value=ready();value.result={...value.result,...patch};assert.equal(handModelReady(value),false);
  }
});
