import {invoke} from '@tauri-apps/api/core';
import type {Proposal, SemanticPorts} from './model';

type Source = {documentId:string;sessionId:string};
type Binding = Source & {runId:string};
interface Owner {semanticBinding():Source|null}
const id=()=>crypto.randomUUID().replaceAll('-','');
const sleep=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms));

/** App-owned ports survive tool routing, with a distinct ID per proposal run. */
export function createSemanticPorts(owner:Owner):SemanticPorts {
  let binding:Binding|null=null, proposal:string|null=null, generation=0;
  const current=(b:Binding)=>{
    const source=owner.semanticBinding();
    return binding===b&&source?.documentId===b.documentId&&source.sessionId===b.sessionId;
  };
  async function request(action:string,b:Binding,extra:Record<string,unknown>={}) {
    const requestId=action==='start'?b.runId:id();
    await invoke('sky_semantic',{requestId,...b,action,device:null,proposalId:null,region:null,regions:null,...extra});
    const deadline=Date.now()+15000;
    while(Date.now()<deadline){
      const value=await invoke<Record<string,unknown>>('sky_semantic_result',{requestId});
      if(value.request_id!==requestId||value.state==='stale')throw Error('自动选区请求已失效；未应用修改');
      if(typeof value.success==='boolean'){
        if(value.success!==true)throw Error(typeof value.error==='string'?value.error:'自动选区请求失败');
        if(action!=='cancel'&&!current(b))throw Error('照片、天空工作区或自动选区运行已变化');
        return value;
      }
      await sleep(40);
    }
    throw Error('自动选区响应超时；未提交任何天空修改');
  }
  return {
    model:action=>invoke('sky_semantic_model',{action}),
    pollModel:()=>invoke('sky_semantic_model_status'),
    async start(device){
      const source=owner.semanticBinding();
      if(!source)throw Error('请先显示天空源图定位，再生成自动选区');
      const b:Binding={...source,runId:id()};
      binding=b;proposal=null;++generation;
      const value=await request('start',b,{device});
      if(typeof value.proposal_id!=='string')throw Error('自动选区缺少运行身份');
      proposal=value.proposal_id;
      return {proposal_id:proposal};
    },
    async cancel(){
      const b=binding;binding=null;proposal=null;++generation;
      if(b)await request('cancel',b); // A stale run ID cannot stop a newer run.
    },
    async shown(proposalId,region){
      if(!binding||proposal!==proposalId)throw Error('自动选区已变化');
      return request('shown',binding,{proposalId,region});
    },
    async accept(proposalId,regions){
      if(!binding||proposal!==proposalId)throw Error('自动选区已变化');
      return await request('accept',binding,{proposalId,regions}) as unknown as Awaited<ReturnType<SemanticPorts['accept']>>;
    },
    async listen(handler){
      let stopped=false,running=false,last:Proposal|null=null;
      const timer=window.setInterval(()=>{
        const b=binding,p=proposal,token=generation;
        if(stopped||running||!b||!p||last?.proposal_id===p)return;
        running=true;
        void invoke<Proposal & {state:string}>('sky_semantic_proposal_status',{...b,proposalId:p}).then(value=>{
          if(stopped||generation!==token)return;
          if(value.state==='running')return;
          const event:Proposal=value.state==='ready'||value.state==='failed'||value.state==='cancelled'
            ? value : {event:'sky_semantic_proposal',proposal_id:p,state:'cancelled',error:'自动选区源会话已失效'};
          if(event.proposal_id!==p)throw Error('自动选区事件身份不一致');
          last=event;handler(event);
        }).catch(error=>{
          if(!stopped&&generation===token){
            last={event:'sky_semantic_proposal',proposal_id:p,state:'failed',error:String(error)};
            handler(last);
          }
        }).finally(()=>{running=false;});
      },120);
      return ()=>{stopped=true;window.clearInterval(timer);};
    },
  };
}
