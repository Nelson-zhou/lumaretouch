import {OPTICS_AUTO_OP,validOpticalReview,type OpticalTargetReview} from '../optics/transferReviewModel';
import {LOCAL_GRADE_OP,validTransferEvidence,sameTransferOptions,type MaskTransferOptions,type MaskTransferEvidence} from '../localMasks/transferModel.ts';
/** Reviewed batch lifecycle. A queued command is not evidence of successful edits. */
export type BatchAction='preflight'|'commit'|'undo';
export type BatchOptions={docs?:string[];moduleScope?:string[];conflictPolicy?:string;batchId?:string;preflightToken?:string;requestId?:string;localMaskTransfer?:MaskTransferOptions};
export type BatchTarget={index:number|null;path:string;document_id:string;revision?:string;blocked?:string|null;
  expected_revision?:string;current_revision?:string|null;result_revision?:string|null;outcome?:string;before?:unknown;local_mask_transfer?:MaskTransferEvidence;optical_transfer?:OpticalTargetReview};
export type BatchReply={request_id:string;action:BatchAction;success:boolean;error?:string;outcome_unknown?:boolean;
  local_mask_transfer?:MaskTransferOptions;preflight_token?:string;source_snapshot?:{document_id:string;revision:string;path:string};source_changed_since_preflight?:boolean;
  module_scope?:string[];applies?:Record<string,unknown>;policy?:string;targets?:unknown[];target_outcomes?:BatchTarget[];
  rejected_docs?:Array<{doc:unknown;error:string}>;ok?:number;blocked?:number;restored?:number[];conflicts?:Array<{path:string;reason:string}>};
export type BatchPlan=Omit<BatchReply,'targets'|'success'|'preflight_token'|'source_snapshot'|'module_scope'|'applies'|'ok'|'blocked'>&{success:true;preflight_token:string;source_snapshot:{document_id:string;revision:string;path:string};
  module_scope:string[];targets:BatchTarget[];applies:Record<string,unknown>;ok:number;blocked:number};
export type BatchContext={docs:string[];moduleScope:string[];conflictPolicy:string;sourceDocumentId:string;enabled:boolean;label:string;localMaskTransfer?:MaskTransferOptions};
export type BatchUi={phase:'closed'|'preflighting'|'review'|'committing'|'uncertain'|'done'|'error';
  hidden?:boolean;operation:BatchAction;plan:BatchPlan|null;result:BatchReply|null;message:string;scopeLabel:string};
export type BatchTransport={request:(action:BatchAction,options:BatchOptions)=>Promise<{requested:boolean}>;
  read:(id:string)=>Promise<{phase:string;request_id:string;result?:BatchReply;error?:string}>};
export function createBatchWorkflow(api:BatchTransport,publish:(state:BatchUi)=>void,
  options:{uuid?:()=>string;pause?:(ms:number)=>Promise<void>;now?:()=>number;timeoutMs?:number}={}){
  const uuid=options.uuid??(()=>crypto.randomUUID());
  const pause=options.pause??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const now=options.now??(()=>performance.now());
  let context:BatchContext={docs:[],moduleScope:[],conflictPolicy:'skip_and_report',sourceDocumentId:'',enabled:false,label:''};
  let key='',generation=0,disposed=false;
  let pending:{id:string;action:BatchAction;generation:number;token?:string;scope?:string[];policy?:string;transfer?:MaskTransferOptions}|null=null;
  let state:BatchUi={phase:'closed',operation:'preflight',plan:null,result:null,message:'',scopeLabel:''};
  const set=(patch:Partial<BatchUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  const active=(g:number)=>!disposed&&g===generation;
  function close(){
    if(state.phase==='committing')return;
    if(state.phase==='uncertain'){set({hidden:true});return;}
    generation++;pending=null;set({phase:'closed',hidden:false,plan:null,result:null,message:''});
  }
  function updateContext(next:BatchContext){
    const nextKey=JSON.stringify([next.docs,next.moduleScope,next.conflictPolicy,next.sourceDocumentId,next.enabled,next.localMaskTransfer]);
    if(key!==nextKey&&['preflighting','review'].includes(state.phase))close();
    context={...next,docs:[...next.docs],moduleScope:[...next.moduleScope]};key=nextKey;
  }
  const identity=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
  const revision=(v:unknown)=>typeof v==='string'&&v.length<=20&&/^\d+$/.test(v)&&BigInt(v)<=18446744073709551615n;
  function planFrom(result:BatchReply,scope:string[],policy:string,transfer?:MaskTransferOptions):BatchPlan{
    if(scope.includes(LOCAL_GRADE_OP)&&!sameTransferOptions(result.local_mask_transfer,transfer))throw Error('局部迁移策略与请求不一致');
    if(!identity(result.preflight_token)||!result.source_snapshot||!identity(result.source_snapshot.document_id)
      ||!revision(result.source_snapshot.revision)||typeof result.source_snapshot.path!=='string'
      ||!Array.isArray(result.targets)||!Array.isArray(result.module_scope)||!result.applies||Array.isArray(result.applies)
      ||JSON.stringify(result.module_scope)!==JSON.stringify(scope)||result.policy!==policy
      ||!Array.isArray(result.rejected_docs)||!Number.isInteger(result.ok)||!Number.isInteger(result.blocked)
      ||(result.ok??-1)<0||(result.blocked??-1)<0||(result.ok??0)+(result.blocked??0)!==result.targets.length
      ||Object.keys(result.applies).sort().join('|')!==[...scope].sort().join('|'))throw Error('预检回执不完整，未允许提交');
    const ids=new Set<string>();let blocked=0;
    for(const item of result.targets){const t=item as BatchTarget;
      if(!t||typeof t.path!=='string'||!identity(t.document_id)||!revision(t.revision)
        ||!Number.isInteger(t.index)||(t.index??-1)<0||ids.has(t.document_id))throw Error('预检目标身份不完整');
      if(scope.includes(LOCAL_GRADE_OP)&&!t.blocked&&(!validTransferEvidence(t.local_mask_transfer)||!sameTransferOptions(t.local_mask_transfer.policy,transfer)))throw Error('缺少匹配的目标局部组预检证据');
      if(scope.includes(OPTICS_AUTO_OP)&&!t.blocked&&!validOpticalReview(t.optical_transfer,t.document_id,t.revision,result.applies[OPTICS_AUTO_OP]))throw Error('缺少匹配的自动镜头/透视目标预检证据');
      ids.add(t.document_id);if(t.blocked)blocked++;
    }
    if(blocked!==result.blocked)throw Error('预检受阻数量不一致');
    return result as BatchPlan;
  }
  function checkCommitted(result:BatchReply){
    const plan=state.plan;
    if(!plan||!Array.isArray(result.target_outcomes)||result.target_outcomes.length!==plan.targets.length
      ||result.source_snapshot?.document_id!==plan.source_snapshot.document_id
      ||result.source_snapshot?.revision!==plan.source_snapshot.revision||result.source_snapshot?.path!==plan.source_snapshot.path)throw Error('提交结果缺少冻结源图或目标明细');
    const reviewed=new Map(plan.targets.map(t=>[t.document_id,t]));
    for(const target of result.target_outcomes){
      const before=reviewed.get(target.document_id);
      if(!before||target.expected_revision!==before.revision||target.path!==before.path
        ||!['applied','skipped'].includes(target.outcome??''))throw Error('提交结果与预检目标不一致');
      reviewed.delete(target.document_id);
    }
  }
  function bounded<T>(promise:Promise<T>,deadline:number):Promise<T>{
    return new Promise<T>((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('通信等待超时，执行结果未确认')),Math.max(1,deadline-now()));
      promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});
    });
  }
  async function poll(request:NonNullable<typeof pending>,deadline=now()+(options.timeoutMs??120000)){
    try{
      while(active(request.generation)){
        const response=await bounded(api.read(request.id),deadline);
        if(!active(request.generation))return;
        if(response.request_id!==request.id)throw Error('批量回执身份不匹配，未确认完成');
        if(response.phase==='done'){
          const result=response.result;
          if(!result||result.request_id!==request.id||result.action!==request.action||typeof result.success!=='boolean')throw Error('批量结果身份不匹配');
          if(result.success&&request.action==='commit'&&result.preflight_token!==request.token)throw Error('批量结果不属于本次预检');
          if(result.success&&request.action==='preflight'){
            const plan=planFrom(result,request.scope??[],request.policy??'',request.transfer);pending=null;set({phase:'review',plan,result:null,message:''});return;
          }
          if(result.outcome_unknown&&request.action!=='preflight'){set({phase:'uncertain',result,message:result.error??'执行结果未确认'});return;}
          if(result.success&&request.action==='commit')checkCommitted(result);
          if(result.success&&request.action==='undo'&&(!Array.isArray(result.restored)||!Array.isArray(result.conflicts)))throw Error('撤销结果缺少逐张明细');
          pending=null;set({phase:result.success?'done':'error',result,message:result.error??''});return;
        }
        if(response.phase!=='pending')throw Error(response.error??'批量结果暂不可查，不能据此判定未执行');
        if(now()>=deadline)throw Error('尚未确认执行结果；可再次查询，不能把排队成功当作完成');
        await pause(150);
      }
    }catch(error){if(active(request.generation)){
      set({phase:'uncertain',message:String(error)});
    }}
  }
  async function submit(action:BatchAction,opts:BatchOptions){
    const g=++generation,id=uuid(),deadline=now()+(options.timeoutMs??120000);
    const request={id,action,generation:g,token:opts.preflightToken,scope:opts.moduleScope,policy:opts.conflictPolicy,transfer:opts.localMaskTransfer};pending=request;
    set({phase:action==='preflight'?'preflighting':'committing',hidden:false,operation:action,result:null,message:''});
    try{
      const accepted=await bounded(api.request(action,{...opts,requestId:id}),deadline);
      if(!active(g))return;
      if(!accepted.requested)throw Error('批量请求未确认入队');
      await poll(request,deadline);
    }catch(error){if(active(g)){
      set({phase:'uncertain',message:String(error)});
    }}
  }
  async function start(){
    if(state.phase==='uncertain'){set({hidden:false});return;}
    if(disposed||['committing','preflighting'].includes(state.phase))return;
    if(!context.enabled||!context.docs.length||!context.moduleScope.length){set({phase:'error',plan:null,result:null,message:'请选择照片与作用范围，并使用支持批量预检的配套引擎'});return;}
    set({plan:null,result:null,scopeLabel:context.label});
    await submit('preflight',{docs:[...context.docs],moduleScope:[...context.moduleScope],conflictPolicy:context.conflictPolicy,localMaskTransfer:context.moduleScope.includes(LOCAL_GRADE_OP)?context.localMaskTransfer:undefined});
  }
  async function commit(){
    if(state.phase!=='review'||!state.plan||state.plan.ok<1)return;
    if(state.plan.policy==='recheck'&&state.plan.blocked>0){set({message:'有受阻目标，请重新预检或修改选择'});return;}
    await submit('commit',{preflightToken:state.plan.preflight_token});
  }
  async function undo(batchId:string){
    if(state.phase==='uncertain'){set({hidden:false});return;}
    if(disposed||!batchId||['committing','preflighting'].includes(state.phase))return;
    set({plan:null,result:null,scopeLabel:''});await submit('undo',{batchId});
  }
  async function query(){
    if(state.phase!=='uncertain'||!pending)return;
    set({phase:pending.action==='preflight'?'preflighting':'committing',hidden:false,message:''});await poll(pending);
  }
  function acknowledgeInspection(){
    if(state.phase!=='uncertain')return;
    generation++;pending=null;set({phase:'closed',hidden:false,result:null,plan:null,message:''});
  }
  return {updateContext,start,commit,undo,query,close,acknowledgeInspection,snapshot:()=>state,dispose:()=>{disposed=true;generation++;pending=null;}};
}
