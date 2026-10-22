/** Reusable one-inflight/full-latest-intent owner. Admission is never completion. */
export type EditContext<R>={documentId:string;faceId:string;recipe:R;revision:number;enabled:boolean};
export type EditIntent<R>={recipe:R;control:string;gestureId:string};
export type EditRequest<R>=EditIntent<R>&{requestId:string;documentId:string;faceId:string;base:R};
export type EditResult<R>={request_id:string;document_id:string;face_id:string;gesture_id:string;control:string;success:boolean;outcome_unknown:boolean;frame_emitted?:boolean;revision?:number;recipe?:R;error?:string};
export type Mailbox<R>={phase:string;request_id:string;result?:EditResult<R>;error?:string};
export type EditView<R>={recipe:R;phase:'idle'|'working'|'uncertain'|'error';message:string};
export function createLatestIntent<R>(ports:{send:(r:EditRequest<R>)=>Promise<unknown>;read:(id:string)=>Promise<Mailbox<R>>;check:(r:unknown)=>R;equal:(a:R,b:R)=>boolean;uuid?:()=>string;pause?:(ms:number)=>Promise<void>;now?:()=>number},initial:R){
  const uuid=ports.uuid??(()=>crypto.randomUUID()),pause=ports.pause??((ms)=>new Promise<void>(r=>setTimeout(r,ms))),now=ports.now??(()=>Date.now());
  let context:EditContext<R>|null=null,confirmed=initial,confirmedRevision=-1,latest:EditIntent<R>|null=null,pending:EditRequest<R>|null=null,polling=false;
  let view:EditView<R>={recipe:initial,phase:'idle',message:''};const listeners=new Set<()=>void>();
  const publish=(patch:Partial<EditView<R>>)=>{view={...view,...patch};listeners.forEach(f=>f());};
  const owns=(p:EditRequest<R>)=>context?.documentId===p.documentId&&context?.faceId===p.faceId;
  function update(c:EditContext<R>){
    const incomingChanged=!context||!ports.equal(c.recipe,context.recipe);
    const changed=context?.documentId!==c.documentId||context?.faceId!==c.faceId;
    context={...c,recipe:ports.check(c.recipe)};
    if(changed){latest=null;confirmed=context.recipe;confirmedRevision=c.revision;publish({recipe:confirmed,message:pending?'原照片请求仍待确认，未将意图转移到新人物':''});}
    if(!pending&&!latest&&(incomingChanged||changed)&&c.revision>=confirmedRevision){confirmed=context.recipe;confirmedRevision=c.revision;publish({recipe:confirmed});}
    if(!pending&&latest&&c.enabled)void flush();
  }
  function bounded<T>(task:Promise<T>,ms:number):Promise<T>{
    return new Promise<T>((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('结果等待超时，只能查询原请求')),Math.max(1,ms));task.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});
  }
  async function poll(){
    if(!pending||polling)return;polling=true;const p=pending,deadline=now()+120000;
    try{
      while(pending===p){
        // Time-bounded read. Timeout retains the original request ID, never retries an edit.
        const reply=await bounded(ports.read(p.requestId),deadline-now());
        if(reply.request_id!==p.requestId)throw Error('结果查询身份不匹配');
        if(reply.phase==='done'){
          const r=reply.result;
          if(!r||r.request_id!==p.requestId||r.document_id!==p.documentId||r.face_id!==p.faceId||r.gesture_id!==p.gestureId||r.control!==p.control||r.outcome_unknown)throw Error(r?.error??'执行结果未确认');
          if(r.success){
            if(!r.frame_emitted||r.recipe===undefined||!Number.isSafeInteger(r.revision))throw Error('缺少已发布预览与实际配方');
            const recipe=ports.check(r.recipe);
            if(!ports.equal(recipe,p.recipe))throw Error('实际配方与原请求不一致，请检查照片');
            if(owns(p)){confirmed=recipe;confirmedRevision=r.revision!;}
            pending=null;
            if(!owns(p)){latest=null;publish({recipe:confirmed,phase:'idle',message:'原照片请求已确认，未继续调整新人物'});}
            else {publish({recipe:latest?.recipe??confirmed,phase:'idle',message:''});}
          }else{
            if(owns(p)&&r.recipe!==undefined&&Number.isSafeInteger(r.revision)){confirmed=ports.check(r.recipe);confirmedRevision=r.revision!;}
            pending=null;latest=null;publish({recipe:confirmed,phase:'error',message:r.error??'修改被拒绝；未重试'});
          }
          break;
        }
        if(reply.phase!=='pending')throw Error(reply.error??'原请求结果不可查；未自动重发');
        if(now()>=deadline)throw Error('执行结果未确认，请查询原请求');
        await pause(100);
      }
    }catch(e){publish({phase:'uncertain',message:String(e)});}
    finally{polling=false;if(!pending&&latest)void flush();}
  }
  async function flush(){
    if(pending||!latest||!context?.enabled||!context.documentId||!context.faceId)return;
    const intent=latest;latest=null;
    if(ports.equal(intent.recipe,confirmed)){publish({phase:'idle',recipe:confirmed});return;}
    const p:EditRequest<R>={...intent,requestId:uuid(),documentId:context.documentId,faceId:context.faceId,base:confirmed};pending=p;
    publish({phase:'working',message:''});
    // Even an invoke rejection can be an uncertain transport outcome. Only read original ID.
    try{await bounded(ports.send(p),10000);}catch(e){publish({phase:'uncertain',message:String(e)});}
    void poll();
  }
  return {update,subscribe:(f:()=>void)=>{listeners.add(f);return()=>{listeners.delete(f);};},snapshot:()=>view,
    edit:(change:(r:R)=>R,control:string,gestureId:string)=>{
      if(!context?.enabled||view.phase==='uncertain'||(pending&&!owns(pending)))return;
      const recipe=ports.check(change(view.recipe));latest={recipe,control,gestureId};publish({recipe});void flush();
    },reconcile:()=>poll(),busy:()=>pending!==null,ownsPending:()=>!pending||owns(pending)};
}
