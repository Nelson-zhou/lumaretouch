import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createProjectActions,type ProjectActionPorts} from './projectActions.ts';
import type {EngineStatus} from '../native';
function fixture(){
  const events:unknown[]=[];
  const p:ProjectActionPorts={choose:async()=>'/photos/Project',command:async(a,o)=>{events.push([a,o]);},
    refresh:async()=>{events.push('refresh');return undefined;},inspect:async()=>({project:{open:true,path:'/p.json',name:'p'}} as EngineStatus),
    name:()=>'',setError:e=>{events.push(['error',e]);},notify:e=>{events.push(['notice',e]);},
    remember:(path,name)=>{events.push(['remember',path,name]);},enterRetouch:()=>{events.push('retouch');}};
  return {p,events};
}
test('create uses directory fallback and remembers only engine-reported project',async()=>{
  const {p,events}=fixture();await createProjectActions(p).createAndRemember();
  assert.deepEqual(events,[['create',{name:'Project',directory:'/photos/Project'}],'refresh','refresh',['remember','/p.json','p']]);
});
test('cancellation preserves existing refresh sequence without sending command',async()=>{
  const {p,events}=fixture();p.choose=async()=>null;await createProjectActions(p).openAndRemember();
  assert.deepEqual(events,['refresh',['remember','/p.json','p']]);
});
test('dialog command errors notify both channels; recent errors do not navigate',async()=>{
  const {p,events}=fixture();p.command=async()=>{throw new Error('unsaved');};
  const actions=createProjectActions(p);await actions.perform('open');
  assert.deepEqual(events,[['error','Error: unsaved'],['notice','Error: unsaved']]);
  events.length=0;await actions.openRecent('/recent.json','recent');
  assert.deepEqual(events,[['error','Error: unsaved']]);
});
test('recent success order and direct save rejection remain explicit',async()=>{
  const {p,events}=fixture();await createProjectActions(p).openRecent('/recent.json','recent');
  assert.deepEqual(events,[['open',{path:'/recent.json'}],'refresh',['remember','/recent.json','recent'],'retouch']);
  p.command=async()=>{throw new Error('disk');};await assert.rejects(createProjectActions(p).save(),/disk/);
});
