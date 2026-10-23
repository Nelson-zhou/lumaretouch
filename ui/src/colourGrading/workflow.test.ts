// UNRUN. Transport/frame race fixtures for the authorized local UI test runner.
import {describe,it,expect} from 'vitest';
import {ColourGradingWorkflow,type Reply} from './workflow';
import {neutral} from './model';
const tick=()=>new Promise<void>(resolve=>queueMicrotask(resolve));
describe('colour grading bounded latest intent',()=>{
  it('coalesces pending previews and refuses stale displayed intent',async()=>{
    const pending:Array<{p:Record<string,unknown>;resolve:(r:Reply)=>void}>=[];const shown:unknown[]=[];
    const owner=new ColourGradingWorkflow({send:p=>new Promise(resolve=>pending.push({p,resolve})),show:async f=>{shown.push(f);},context:()=>({document:'d',revision:0}),message:()=>{},committed:()=>{}});
    owner.preview(neutral());const newer=neutral();newer.global.saturation=50;owner.preview(newer);owner.preview({...newer,balance:50});
    expect(pending).toHaveLength(1);
    const finish=(i:number)=>{const q=pending[i];q.resolve({event:'colour_grading_preview',request_id:String(q.p.request_id),document_id:'d',revision:0,preview_id:String(q.p.request_id),frame:{i}});};
    finish(0);await tick();await tick();expect(shown).toHaveLength(0);expect(pending).toHaveLength(2);
    expect((pending[1].p.recipe as {balance:number}).balance).toBe(50);
    finish(1);await tick();await tick();expect(shown).toHaveLength(1);expect(owner.canApply).toBe(true);
  });
  it('does not publish a preview after switching document',async()=>{
    let doc='a';let finish:(r:Reply)=>void=()=>{};let request:Record<string,unknown>={};let displays=0;
    const owner=new ColourGradingWorkflow({send:p=>{request=p;return new Promise(resolve=>{finish=resolve;});},show:async()=>{displays++;},context:()=>({document:doc,revision:0}),message:()=>{},committed:()=>{}});
    owner.preview(neutral());doc='b';owner.invalidate();finish({event:'colour_grading_preview',request_id:String(request.request_id),document_id:'a',revision:0,preview_id:String(request.request_id),frame:{}});
    await tick();await tick();expect(displays).toBe(0);expect(owner.canApply).toBe(false);
  });
});
