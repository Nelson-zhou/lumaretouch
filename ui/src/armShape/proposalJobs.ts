// SPDX-License-Identifier: GPL-3.0-or-later
import {command,type Command,type Reply,type createArmPort} from './nativeTransport';
import {refKey,type ProposalResult,type Request} from './model';
type Job={request:Request;start:Command;accepted:boolean;cancelRequested:boolean;cancel:Command|null;cancelSettled:boolean;result:ProposalResult;uncertain:boolean};
/** App-owned jobs survive the source-review popup. Cancellation and start are each sent once. */
export function createProposalJobs(port:ReturnType<typeof createArmPort>,allowed:(request:Request)=>boolean,changed:()=>void){
 const jobs=new Map<string,Job>(),queries=new Map<string,Promise<ProposalResult>>(),seen=new Set<string>(),released=new Map<string,ProposalResult>();
 const pending=(job:Job)=>job.result.phase==='pending'||job.uncertain||job.cancelRequested&&!job.cancelSettled;
 function read(job:Job,reply:Reply,kind:'start'|'status'|'cancel'):ProposalResult{
  const result=reply.result?.proposal,id=job.request.request_id;
  if(reply.action!==`proposal_${kind}`||reply.outcome_unknown||!result||result.job_id!==id||!['pending','done','unavailable'].includes(result.phase)||typeof result.success!=='boolean'){
   if(kind==='start'&&reply.action==='proposal_start'&&!reply.success&&!reply.outcome_unknown){job.accepted=true;job.result={phase:'done',job_id:id,success:false,error:reply.error??'未启动选区生成。'};job.uncertain=false;changed();return job.result;}
   throw Error(reply.error??'选区任务回执不匹配，只能继续查询原任务。');
  }
  if(result.proposal){const p=result.proposal,c=result.context,r=job.request;
   if(!c||c.document_id!==r.document_id||c.document_epoch!==r.document_epoch||c.body_graph_sha256!==r.body_graph_sha256||c.people_graph_sha256!==r.people_graph_sha256||refKey(p.body_ref)!==refKey(r.body_ref)||p.source.sha256!==r.body_ref.asset_sha256||p.segment!==r.payload.segment)throw Error('选区回执来源或人物状态不一致，不能复核。');
  }
  // An unavailable job lookup cannot prove that a lost start never executed.
  if(!job.accepted&&kind==='status'&&result.phase==='unavailable')throw Error('启动回执仍待确认；任务暂不可查，不会重新生成。');
  job.accepted=true;job.result=result;job.uncertain=false;if(kind==='cancel')job.cancelSettled=true;changed();return result;
 }
 async function query(job:Job):Promise<ProposalResult>{
  try{
   // Backend cancellation tombstones also fence a lost or delayed start.
   if(job.cancelRequested&&!job.cancelSettled){
    let reply:Reply|null;
    if(!job.cancel){job.cancel=command('proposal_cancel',{job_id:job.request.request_id});reply=await port.send(job.cancel);}else reply=await port.status(job.cancel.request_id);
    if(!reply)return job.result;
    read(job,reply,'cancel');void port.release(job.cancel.request_id);void port.release(job.start.request_id);
    // Preserve a bounded, small tombstone, never the released multi-mask payload.
    job.result={phase:'done',job_id:job.request.request_id,success:false,error:'选区任务已取消并释放，未应用新的身体调整。'};
    released.set(job.request.request_id,job.result);jobs.delete(job.request.request_id);changed();return job.result;
   }
   if(!job.accepted){let reply:Reply|null=null;try{reply=await port.status(job.start.request_id);}catch{/* A job lookup is read-only, never another start. */}
    if(reply&&!reply.outcome_unknown){read(job,reply,'start');void port.release(job.start.request_id);}else{
     const wire=command('proposal_status',{job_id:job.request.request_id});const reply=await port.send(wire);try{read(job,reply,'status');}finally{void port.release(wire.request_id);}
    }
   }
   if(job.result.phase==='pending'){
    const wire=command('proposal_status',{job_id:job.request.request_id});const reply=await port.send(wire);try{read(job,reply,'status');}finally{void port.release(wire.request_id);}
   }
   return job.result;
  }catch(error){job.uncertain=true;changed();throw error;}
 }
 const status=(id:string):Promise<ProposalResult>=>{
  const job=jobs.get(id);if(!job){const result=released.get(id);return result?Promise.resolve(result):Promise.reject(Error('没有对应的原选区任务，不能重新生成。'));}
  const old=queries.get(id);if(old)return old;
  if(!pending(job))return Promise.resolve(job.result);
  const work=query(job);queries.set(id,work);void work.then(()=>queries.delete(id),()=>queries.delete(id));return work;
 };
 return {
  async start(request:Request):Promise<ProposalResult>{
   if(seen.has(request.request_id))throw Error('不会重新发送已存在或已释放的选区任务。');
   if(seen.size>=4096||jobs.size>=4)return {phase:'done',job_id:request.request_id,success:false,error:'选区任务保留额度已满，请关闭已有复核窗口；不会丢弃原任务身份。'};
   if(!allowed(request)||[...jobs.values()].some(pending))return {phase:'done',job_id:request.request_id,success:false,error:'请先等待其他工具和原选区任务完成，未启动新任务。'};
   const wire=command('proposal_start',request),job:Job={request,start:wire,accepted:false,cancelRequested:false,cancel:null,cancelSettled:false,result:{phase:'pending',job_id:request.request_id,success:false},uncertain:false};seen.add(request.request_id);jobs.set(request.request_id,job);changed();
   try{const reply=await port.send(wire);const result=job.accepted?job.result:read(job,reply,'start');void port.release(wire.request_id);return result;}catch(error){if(job.accepted)return job.result;job.uncertain=true;changed();throw error;}
  },status,
  cancel(id:string){const job=jobs.get(id);if(!job)return Promise.resolve(released.get(id)??{phase:'unavailable',job_id:id,success:false,error:'没有对应的原选区任务。'} as ProposalResult);job.cancelRequested=true;changed();const query=queries.get(id);return query?query.catch(()=>job.result).then(()=>status(id)):status(id);},
  active:()=>[...jobs.values()].filter(pending).map(job=>job.request.request_id),
  retained:()=>[...jobs.keys()],
  uncertain:()=>[...jobs.values()].some(job=>job.uncertain),
 };
}
