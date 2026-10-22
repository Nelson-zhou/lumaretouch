import {describe,it,expect} from 'vitest';
import {createLatestIntent,type EditRequest,type Mailbox} from '../browShape/latestIntent';
import {neutral,check,adjust,link,type MouthShape} from './model';
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
function fixture(){
  const sent:EditRequest<MouthShape>[]=[];const reads=new Map<string,(v:Mailbox<MouthShape>)=>void>();let n=0;
  const owner=createLatestIntent<MouthShape>({check,equal:(a,b)=>JSON.stringify(a)===JSON.stringify(b),uuid:()=>`r${++n}`,
    send:async p=>{sent.push(p);return {requested:true};},read:id=>new Promise(r=>reads.set(id,r))},neutral());
  const context={documentId:'doc',faceId:'face',recipe:neutral(),revision:1,enabled:true};owner.update(context);
  const finish=(i:number,revision:number)=>{const p=sent[i];reads.get(p.requestId)!({phase:'done',request_id:p.requestId,result:{request_id:p.requestId,document_id:p.documentId,face_id:p.faceId,gesture_id:p.gestureId,control:p.control,success:true,outcome_unknown:false,frame_emitted:true,recipe:p.recipe,revision}});};
  return {owner,sent,reads,finish,context};
}
describe('one-inflight confirmed latest intent (source added, not executed)',()=>{
  it('retains only final drag intent and uses actual first receipt as next CAS base',async()=>{
    const f=fixture();f.owner.edit(r=>adjust(r,'vertical',.1),'vertical','gesture');await tick();
    for(let i=2;i<=100;i++)f.owner.edit(r=>adjust(r,'vertical',i/100),'vertical','gesture');
    expect(f.sent).toHaveLength(1);expect(f.owner.snapshot().phase).toBe('working');
    f.finish(0,2);await tick();expect(f.sent).toHaveLength(2);
    expect(f.sent[1].base).toEqual(f.sent[0].recipe);expect(f.sent[1].recipe.vertical).toBe(1);
    expect(f.sent[1].gestureId).toBe('gesture');f.finish(1,3);await tick();
    expect(f.owner.busy()).toBe(false);
    f.owner.update({...f.context,recipe:f.sent[0].recipe,revision:2});
    expect(f.owner.snapshot().recipe.vertical).toBe(1); // late frame cannot regress receipt
  });
  it('preserves pending unlock, unequal values and non-destructive relink',async()=>{
    const f=fixture();f.owner.edit(r=>link(r,false),'gummy','unlock');await tick();
    f.owner.edit(r=>adjust(r,'gummy',.7,'left'),'gummy','left');
    f.owner.edit(r=>adjust(r,'gummy',.3,'right'),'gummy','right');
    f.owner.edit(r=>link(r,true),'gummy','relink');
    f.finish(0,2);await tick();expect(f.sent[1].recipe.gummy).toEqual({linked:true,left:.7,right:.3});
    f.finish(1,3);await tick();
  });
  it('retains uncertain original ID and never resends the edit',async()=>{
    const f=fixture();f.owner.edit(r=>adjust(r,'vertical',.2),'vertical','g');await tick();
    const p=f.sent[0];f.reads.get(p.requestId)!({phase:'unavailable',request_id:p.requestId});await tick();
    expect(f.owner.snapshot().phase).toBe('uncertain');f.owner.edit(()=>neutral(),'all','reset');
    void f.owner.reconcile();await tick();expect(f.sent).toHaveLength(1);f.finish(0,2);await tick();
    expect(f.owner.busy()).toBe(false);
  });
  it('does not transfer unsent intent when source or selected person changes',async()=>{
    const f=fixture();f.owner.edit(r=>adjust(r,'width',.2),'width','g');await tick();
    f.owner.edit(r=>adjust(r,'width',.8),'width','g');
    f.owner.update({...f.context,faceId:'another'});f.finish(0,2);await tick();
    expect(f.sent).toHaveLength(1);expect(f.owner.snapshot().recipe).toEqual(neutral());
  });
});
