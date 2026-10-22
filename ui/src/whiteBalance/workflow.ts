export type Algorithm='legacy-xyz-ratio-v1'|'linear-srgb-d-white-ratio-v1';
export type Request={request_id:string;document_id:string;action:'set_algorithm'|'reset'|'clear_pick';algorithm?:Algorithm};
export type Context={enabled:boolean;documentId:string;reason?:string};
export type State={phase:'idle'|'sending'|'waiting'|'success'|'failure'|'uncertain';message:string;request?:Request};
export type Ports={send:(r:Request)=>Promise<unknown>;query:(id:string)=>Promise<unknown>;refresh:()=>Promise<void>;id:()=>string;sleep:(ms:number)=>Promise<void>;timeoutMs?:number};
const object=(x:unknown):x is Record<string,unknown>=>!!x&&typeof x==='object'&&!Array.isArray(x);
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('白平衡请求超时，结果尚未确认')),Math.max(1,milliseconds));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
export function createWhiteBalanceWorkflow(ports:Ports){
  let context:Context={enabled:false,documentId:''};let state:State={phase:'idle',message:''};let running=false;let generation=0;let active=true;const timeout=ports.timeoutMs??10000;
  const listeners=new Set<(s:State)=>void>();
  const publish=(s:State)=>{state=s;listeners.forEach(f=>f(s));};
  const busy=()=>running||['sending','waiting','uncertain'].includes(state.phase);
  async function query(request:Request){
    if(!active||running)return;const token=generation;const deadline=Date.now()+timeout;running=true;publish({phase:'waiting',request,message:'正在确认白平衡结果…'});
    try{
      for(let i=0;i<100;i++){
        if(token!==generation)return;
        if(Date.now()>=deadline)throw Error('等待白平衡结果超时');
        const packet=await bounded(ports.query(request.request_id),deadline-Date.now());
        if(token!==generation)return;
        if(!object(packet)||packet.request_id!==request.request_id)throw Error('白平衡回执身份不匹配');
        if(packet.phase==='pending'){await bounded(ports.sleep(100),deadline-Date.now());continue;}
        if(packet.phase!=='done'||!object(packet.result))throw Error('白平衡回执丢失或引擎已重启');
        const r=packet.result;
        if(r.protocol!==1||r.request_id!==request.request_id||r.document_id!==request.document_id||r.action!==request.action||typeof r.success!=='boolean'||typeof r.outcome_unknown!=='boolean')throw Error('白平衡回执不完整');
        if(r.outcome_unknown)throw Error(typeof r.error==='string'?r.error:'调整结果未确认');
        if(!r.success){publish({phase:'failure',request,message:typeof r.error==='string'?r.error:'白平衡未提交'});return;}
        if(r.requires_reload!==false)throw Error('白平衡画面需要重新载入');
        if(!object(r.after)||!object(r.after.options))throw Error('白平衡结果缺少参数证据');
        if(request.action==='set_algorithm'&&r.after.options.algorithm!==request.algorithm)throw Error('白平衡算法结果与请求不符');
        if(request.action==='reset'&&(r.after.temperature_shift!==0||r.after.tint_shift!==0||!Array.isArray(r.after.options.picked_gains)||r.after.options.picked_gains.length!==3||!r.after.options.picked_gains.every(v=>v===1)))throw Error('白平衡重置结果不完整');
        if(request.action==='clear_pick'&&(!Array.isArray(r.after.options.picked_gains)||r.after.options.picked_gains.length!==3||!r.after.options.picked_gains.every(v=>v===1)))throw Error('中性点清除结果不完整');
        let refreshFailed=false;
        try{await bounded(ports.refresh(),Math.min(timeout,3000));}catch{refreshFailed=true;}
        if(token!==generation)return;
        let message=context.documentId===request.document_id?'白平衡调整已完成':'上一张照片的白平衡调整已完成';
        if(refreshFailed)message+='；状态刷新失败，请稍后重试刷新';
        publish({phase:'success',request,message});return;
      }
      throw Error('等待结果超时，未自动重发调整');
    }catch(error){if(token===generation)publish({phase:'uncertain',request,message:String(error)});}finally{if(token===generation)running=false;}
  }
  return {
    snapshot:()=>state,
    generation:()=>generation,
    activate(){active=true;},
    stop(){active=false;generation++;running=false;if(state.request&&['sending','waiting'].includes(state.phase))state={...state,phase:'uncertain',message:'界面已中断等待；请查询原操作结果，不会重发'};},
    reportUIError:(error:unknown)=>{if(active&&!busy())publish({phase:'failure',message:String(error)});},
    subscribe:(f:(s:State)=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},
    context:(next:Context)=>{context=next;},
    busy,
    async start(action:Request['action'],algorithm:Algorithm|undefined,expectedDocument:string,expectedGeneration=generation){
      if(!active||expectedGeneration!==generation||busy())return;
      if(!context.enabled||!context.documentId||context.documentId!==expectedDocument){publish({phase:'failure',message:'照片或编辑状态已变化，未提交调整'});return;}
      const request:Request={request_id:ports.id(),document_id:context.documentId,action,...(algorithm?{algorithm}: {})};
      const token=generation;publish({phase:'sending',request,message:'正在提交白平衡调整…'});running=true;
      try{await bounded(ports.send(request),timeout);}catch(error){if(token===generation){publish({phase:'uncertain',request,message:`提交结果未确认：${String(error)}`});running=false;}return;}
      if(token!==generation)return;
      running=false;await query(request);
    },
    async check(){if(active&&state.request&&!running)await query(state.request);},
    acknowledgeAfterReload(){
      if(active&&state.phase==='uncertain'&&!running&&state.request&&context.enabled&&context.documentId!==state.request.document_id){publish({phase:'idle',message:'已切换至重新打开的照片；不会重发旧调整'});}
    },
  };
}
