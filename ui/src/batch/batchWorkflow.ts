import {sameAssociationReview,validAssociationReview,type AssociationReview,type AssociationTarget} from '../people/associationProof';
import {CROP_OP,CROP_LIMITS,sourceProof,validCropReview,type CropReview} from '../cropTransfer/model.ts';
import {samePeopleRequest,validPeopleReview,peopleProofDocument,type PeopleTransferRequest,type PeopleTransferProof,type PeopleTransferReview} from '../people/transferProof.ts';
import {validReferenceReview,type ReferenceReview} from '../referenceColor/ReferenceColorReview';
import {OPTICS_AUTO_OP,validOpticalReview,type OpticalTargetReview} from '../optics/transferReviewModel';
import {LOCAL_GRADE_OP,validTransferEvidence,sameTransferOptions,type MaskTransferOptions,type MaskTransferEvidence} from '../localMasks/transferModel.ts';
import {SPILL_TRANSFER_OP as SPILL_OP,SPILL_TRANSFER_LIMITS,spillTransferParameters,validSpillTransfer,validSpillTransferAck,type SpillTransferEvidence,type SpillTransferAck} from '../spillRemoval/transferModel.ts';
import {SHADOW_TRANSFER_OP as SHADOW_OP,SHADOW_TRANSFER_LIMITS,shadowTransferParameters,validShadowTransfer,validShadowTransferAck,type ShadowTransferEvidence,type ShadowTransferAck} from '../originalShadow/transferModel.ts';
/** Reviewed batch lifecycle. A queued command is not evidence of successful edits. */
export type BatchAction='preflight'|'commit'|'undo'|'redo';
export type BatchOptions={docs?:string[];moduleScope?:string[];conflictPolicy?:string;batchId?:string;preflightToken?:string;requestId?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest;spillReviewAck?:SpillTransferAck[];shadowReviewAck?:ShadowTransferAck[]};
export type BatchTarget={index:number|null;path:string;document_id:string;revision?:string;blocked?:string|null;
  source_proof?:unknown;expected_revision?:string;current_revision?:string|null;result_revision?:string|null;outcome?:string;before?:unknown;spill_transfer?:SpillTransferEvidence;shadow_transfer?:ShadowTransferEvidence;crop_transfer?:CropReview;local_mask_transfer?:MaskTransferEvidence;optical_transfer?:OpticalTargetReview;reference_color?:ReferenceReview;people_transfer?:PeopleTransferReview|null;association?:AssociationTarget['association']};
type BatchSource={document_id:string;revision:string;path:string;source_proof?:unknown};
export type BatchReply={batch_id?:string;request_id:string;action:BatchAction;success:boolean;error?:string;outcome_unknown?:boolean;
  persistent_association?:AssociationReview;association_source?:BatchTarget;source_outcome?:BatchTarget;people_transfer?:boolean;local_mask_transfer?:MaskTransferOptions;preflight_token?:string;source_snapshot?:BatchSource;source_changed_since_preflight?:boolean;
  module_scope?:string[];applies?:Record<string,unknown>;policy?:string;targets?:unknown[];target_outcomes?:BatchTarget[];
  rejected_docs?:Array<{doc:unknown;error:string}>;ok?:number;blocked?:number;restored?:number[];conflicts?:Array<{path:string;reason:string}>};
export type BatchPlan=Omit<BatchReply,'targets'|'success'|'preflight_token'|'source_snapshot'|'module_scope'|'applies'|'ok'|'blocked'>&{success:true;preflight_token:string;source_snapshot:BatchSource;
  module_scope:string[];targets:BatchTarget[];applies:Record<string,unknown>;ok:number;blocked:number};
export type BatchContext={docs:string[];moduleScope:string[];conflictPolicy:string;sourceDocumentId:string;enabled:boolean;label:string;referencePath?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest;peopleProof?:PeopleTransferProof};
export type BatchUi={phase:'closed'|'preflighting'|'review'|'committing'|'uncertain'|'done'|'error';
  hidden?:boolean;operation:BatchAction;plan:BatchPlan|null;result:BatchReply|null;message:string;scopeLabel:string};
export type BatchTransport={request:(action:BatchAction,options:BatchOptions)=>Promise<{requested:boolean}>;
  read:(id:string)=>Promise<{phase:string;request_id:string;result?:BatchReply;error?:string}>};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
function sameSourceProof(a:unknown,b:unknown){
  return sourceProof(a)&&sourceProof(b)&&a.asset_sha256===b.asset_sha256&&a.original_sha256===b.original_sha256
    &&(a.creative_source===null?b.creative_source===null:b.creative_source!==null
      &&a.creative_source.sha256===b.creative_source.sha256&&a.creative_source.width===b.creative_source.width
      &&a.creative_source.height===b.creative_source.height);
}
export function createBatchWorkflow(api:BatchTransport,publish:(state:BatchUi)=>void,
  options:{uuid?:()=>string;pause?:(ms:number)=>Promise<void>;now?:()=>number;timeoutMs?:number}={}){
  const uuid=options.uuid??(()=>crypto.randomUUID());
  const pause=options.pause??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const now=options.now??(()=>performance.now());
  let context:BatchContext={docs:[],moduleScope:[],conflictPolicy:'skip_and_report',sourceDocumentId:'',enabled:false,label:''};
  let key='',generation=0,disposed=false;
  let pending:{id:string;action:BatchAction;generation:number;contextKey:string;token?:string;scope?:string[];policy?:string;transfer?:MaskTransferOptions;reference?:{strength:number};people?:PeopleTransferRequest;peopleProof?:PeopleTransferProof;referencePath?:string;docs?:string[]}|null=null;
  let state:BatchUi={phase:'closed',operation:'preflight',plan:null,result:null,message:'',scopeLabel:''};
  const set=(patch:Partial<BatchUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  const active=(g:number)=>!disposed&&g===generation;
  function close(){
    if(state.phase==='committing')return;
    if(state.phase==='uncertain'){set({hidden:true});return;}
    generation++;pending=null;set({phase:'closed',hidden:false,plan:null,result:null,message:''});
  }
  function updateContext(next:BatchContext){
    const nextKey=JSON.stringify([next.docs,next.moduleScope,next.conflictPolicy,next.sourceDocumentId,next.enabled,next.localMaskTransfer,next.referenceColor,next.referencePath,next.peopleTransfer,next.peopleProof]);
    if(key!==nextKey&&['preflighting','review'].includes(state.phase))close();
    context={...next,docs:[...next.docs],moduleScope:[...next.moduleScope]};key=nextKey;
  }
  const identity=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{32}$/.test(v);
  const revision=(v:unknown)=>typeof v==='string'&&v.length<=20&&/^\d+$/.test(v)&&BigInt(v)<=18446744073709551615n;
  function planFrom(result:BatchReply,scope:string[],policy:string,transfer?:MaskTransferOptions,reference?:{strength:number},people?:PeopleTransferRequest,peopleProof?:PeopleTransferProof,referencePath?:string,docs?:string[]):BatchPlan{
    if(scope.includes(LOCAL_GRADE_OP)&&!sameTransferOptions(result.local_mask_transfer,transfer))throw Error('局部迁移策略与请求不一致');
    if(!identity(result.preflight_token)||!result.source_snapshot||!identity(result.source_snapshot.document_id)
      ||!revision(result.source_snapshot.revision)||typeof result.source_snapshot.path!=='string'
      ||!Array.isArray(result.targets)||!Array.isArray(result.module_scope)||!result.applies||Array.isArray(result.applies)
      ||JSON.stringify(result.module_scope)!==JSON.stringify(scope)||result.policy!==policy
      ||!Array.isArray(result.rejected_docs)||!Number.isInteger(result.ok)||!Number.isInteger(result.blocked)
      ||(result.ok??-1)<0||(result.blocked??-1)<0||(result.ok??0)+(result.blocked??0)!==result.targets.length
      ||(!people&&Object.keys(result.applies).sort().join('|')!==[...scope].sort().join('|')))throw Error('预检回执不完整，未允许提交');
    const spill=scope.includes(SPILL_OP);
    if(spill&&(scope.includes('lnx.id_background.v1')||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!spillTransferParameters(result.applies[SPILL_OP])))throw Error('祛反光预检缺少真实源图证明或包含非标量参数');
    if(spill&&result.targets.length>SPILL_TRANSFER_LIMITS.targets)throw Error('祛反光审核最多同时选择 8 张目标，不能省略逐图审核');
    const shadow=scope.includes(SHADOW_OP);
    if(shadow&&((scope.includes('lnx.id_background.v1')||scope.includes(SPILL_OP))||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!shadowTransferParameters(result.applies[SHADOW_OP])))throw Error('原图阴影预检缺少真实源图证明或包含非标量参数');
    if(shadow&&result.targets.length>SHADOW_TRANSFER_LIMITS.targets)throw Error('原图阴影审核最多同时选择 8 张目标，不能省略逐图审核');
    if(people&&(!peopleProof||result.people_transfer!==true||!samePeopleRequest(result.applies,people)
      ||result.source_snapshot.document_id!==peopleProofDocument(peopleProof).document_id
      ||result.source_snapshot.revision!==String(peopleProofDocument(peopleProof).revision)))throw Error('人物迁移源图、关联或参数选择与请求不符');
    if(people?.target_policy!=='persistent_association'&&(result.persistent_association||result.association_source))throw Error('未请求的持久关联回执');
    if(!people&&result.people_transfer)throw Error('未请求的人物迁移回执');
    if(reference&&(result.applies?.['lnx.reference_color.v1'] as {strength?:number})?.strength!==reference.strength)throw Error('参考统一程度与请求不同');
    if(referencePath&&result.source_snapshot.path!==referencePath)throw Error('源图与冻结请求不同');
    const exactPeopleTargets=people&&(people.target_policy==='explicit_face_map'||people.target_policy==='persistent_association')?new Set(people.targets.map(row=>row.target.document.document_id)):null;
    if(exactPeopleTargets&&(!docs||docs.length!==exactPeopleTargets.size||new Set(docs).size!==docs.length
      ||docs.some(id=>!exactPeopleTargets.has(id))))throw Error('本次配对没有覆盖准确的目标照片名单');
    if(scope.includes(CROP_OP)&&result.targets.length>CROP_LIMITS.targets)throw Error('裁剪审核不能省略目标预览，请减少目标数量');
    const ids=new Set<string>();let blocked=0;
    for(const item of result.targets){const t=item as BatchTarget;
      if(!t||typeof t.path!=='string'||!identity(t.document_id)||!revision(t.revision)
        ||!Number.isInteger(t.index)||(t.index??-1)<0||ids.has(t.document_id))throw Error('预检目标身份不完整');
      if(exactPeopleTargets&&!exactPeopleTargets.delete(t.document_id))throw Error('预检加入了未指定的人物目标');
      if(spill&&t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked))throw Error('祛反光目标受阻状态无效');
      if(spill&&!t.blocked){
        const before=object(t.before)?t.before[SPILL_OP]:null;
        if(!sourceProof(t.source_proof)||!object(before)||Object.keys(before).length!==1||!hash(before.target_recipe_key)
          ||t.document_id===result.source_snapshot.document_id&&!sameSourceProof(t.source_proof,result.source_snapshot.source_proof))
          throw Error('祛反光目标缺少自己的来源证明或冻结背景依赖');
        if(!validSpillTransfer(t.spill_transfer,t.document_id,t.revision,result.applies[SPILL_OP],t.source_proof))
          throw Error('祛反光目标缺少匹配本图、参数及来源的真实前后预览');
      }
      if(shadow&&t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked))throw Error('原图阴影目标受阻状态无效');
      if(shadow&&!t.blocked){
        const before=object(t.before)?t.before[SHADOW_OP]:null;
        if(!sourceProof(t.source_proof)||!object(before)||Object.keys(before).length!==1||!hash(before.target_recipe_key)
          ||t.document_id===result.source_snapshot.document_id&&!sameSourceProof(t.source_proof,result.source_snapshot.source_proof))
          throw Error('原图阴影目标缺少自己的来源证明或冻结背景依赖');
        if(!validShadowTransfer(t.shadow_transfer,t.document_id,t.revision,result.applies[SHADOW_OP],t.source_proof))
          throw Error('原图阴影目标缺少匹配本图、参数及来源的真实前后预览');
      }
      if(scope.includes(LOCAL_GRADE_OP)&&!t.blocked&&(!validTransferEvidence(t.local_mask_transfer)||!sameTransferOptions(t.local_mask_transfer.policy,transfer)))throw Error('缺少匹配的目标局部组预检证据');
      if(scope.includes(OPTICS_AUTO_OP)&&!t.blocked&&!validOpticalReview(t.optical_transfer,t.document_id,t.revision,result.applies[OPTICS_AUTO_OP]))throw Error('缺少匹配的自动镜头/透视目标预检证据');
      if(scope.includes('lnx.reference_color.v1')&&!t.blocked&&(result.applies['lnx.reference_color.v1'] as {strength?:number})?.strength!==0&&!validReferenceReview(t.reference_color,t.document_id,t.revision??''))throw Error('缺少匹配的参考统一目标预检证据');
      if(scope.includes(CROP_OP)&&!t.blocked&&!validCropReview(t.crop_transfer,t.document_id,t.revision,result.applies[CROP_OP]))throw Error('缺少匹配的本目标真实裁剪预览');
      if(people&&people.target_policy!=='persistent_association'&&!t.blocked&&(!peopleProof||!validPeopleReview(t.people_transfer,people,peopleProof,t)))throw Error('缺少已确认人物及逐项参数的目标预检证据');
      ids.add(t.document_id);if(t.blocked)blocked++;
    }
    if(exactPeopleTargets){
      for(const rejected of result.rejected_docs??[]){
        if(!rejected||typeof rejected.doc!=='string'||!exactPeopleTargets.delete(rejected.doc)
          ||typeof rejected.error!=='string'||!rejected.error)throw Error('无效目标回执与本次配对不符');
      }
      if(exactPeopleTargets.size)throw Error('预检遗漏了本次明确指定的目标照片');
    }
    if(people?.target_policy==='persistent_association'&&(policy!=='recheck'||blocked||result.rejected_docs?.length||!result.association_source
      ||!validAssociationReview(result.persistent_association,people,result.association_source,result.targets as BatchTarget[])))throw Error('持久人物关联缺少完整的源图、成员及共享参数审核');
    if(blocked!==result.blocked)throw Error('预检受阻数量不一致');
    return result as BatchPlan;
  }
  function checkCommitted(result:BatchReply){
    const plan=state.plan;
    if(!plan||!Array.isArray(result.target_outcomes)||result.target_outcomes.length!==plan.targets.length
      ||result.source_snapshot?.document_id!==plan.source_snapshot.document_id
      ||result.source_snapshot?.revision!==plan.source_snapshot.revision||result.source_snapshot?.path!==plan.source_snapshot.path)throw Error('提交结果缺少冻结源图或目标明细');
    if(plan.module_scope.includes(SPILL_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('祛反光提交来源证明与冻结预检不同');
    if(plan.module_scope.includes(SHADOW_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('原图阴影提交来源证明与冻结预检不同');
    if(plan.persistent_association){const source=result.source_outcome,before=plan.association_source;
      if(!sameAssociationReview(result.persistent_association,plan.persistent_association))throw Error('持久关联提交内容或版本与冻结审核不同');
      if(!source||!before||source.document_id!==before.document_id||source.path!==before.path||source.expected_revision!==before.revision||source.outcome!=='applied'||!revision(source.result_revision)||BigInt(source.result_revision)<=BigInt(before.revision??'0'))throw Error('持久关联缺少源成员的实际提交结果');}
    const reviewed=new Map(plan.targets.map(t=>[t.document_id,t]));
    for(const target of result.target_outcomes){
      const before=reviewed.get(target.document_id);
      if(!before||target.expected_revision!==before.revision||target.path!==before.path
        ||!['applied','skipped'].includes(target.outcome??''))throw Error('提交结果与预检目标不一致');
      if(plan.persistent_association&&(target.outcome!=='applied'||!revision(target.result_revision)||BigInt(target.result_revision)<=BigInt(before.revision??'0')))throw Error('持久关联成员未全部提交，结果需要检查');
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
            if(request.contextKey!==key){pending=null;set({phase:'error',plan:null,result:null,message:'源图、目标或参数选择已经变化，旧预检不会用于提交；请重新预检。'});return;}
            try{
              const plan=planFrom(result,request.scope??[],request.policy??'',request.transfer,request.reference,request.people,request.peopleProof,request.referencePath,request.docs);
              pending=null;set({phase:'review',plan,result:null,message:''});
            }catch(error){pending=null;set({phase:'error',plan:null,result:null,message:String(error)});}
            return;
          }
          if(result.outcome_unknown&&request.action!=='preflight'){set({phase:'uncertain',result,message:result.error??'执行结果未确认'});return;}
          if(result.success&&request.action==='commit')checkCommitted(result);
          if(result.success&&['undo','redo'].includes(request.action)&&(!Array.isArray(result.restored)||!Array.isArray(result.conflicts)))throw Error('撤销结果缺少逐张明细');
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
    const request={id,action,generation:g,contextKey:key,token:opts.preflightToken,scope:opts.moduleScope,policy:opts.conflictPolicy,transfer:opts.localMaskTransfer,reference:opts.referenceColor,people:opts.peopleTransfer,peopleProof:context.peopleProof,referencePath:context.referencePath,docs:opts.docs};pending=request;
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
    if(!context.enabled||!context.docs.length||(!context.moduleScope.length&&!(context.peopleTransfer?.target_policy==='persistent_association'&&context.peopleTransfer.operation==='unlink'))){set({phase:'error',plan:null,result:null,message:'请选择照片与作用范围，并使用支持批量预检的配套引擎'});return;}
    if(context.moduleScope.includes(SPILL_OP)&&context.docs.length>SPILL_TRANSFER_LIMITS.targets){set({phase:'error',plan:null,result:null,message:'祛反光审核每批最多 8 张目标，请减少选择；不会只审核前几张。'});return;}
    if(context.moduleScope.includes(SHADOW_OP)&&context.docs.length>SHADOW_TRANSFER_LIMITS.targets){set({phase:'error',plan:null,result:null,message:'原图阴影审核每批最多 8 张目标，请减少选择；不会只审核前几张。'});return;}
    if(context.moduleScope.includes(SHADOW_OP)&&context.moduleScope.some(op=>[SPILL_OP,'lnx.id_background.v1'].includes(op))){set({phase:'error',plan:null,result:null,message:'原图阴影标量不能与祛染或整套背景一起同步，请分别预检并审核。'});return;}
    set({plan:null,result:null,scopeLabel:context.label});
    await submit('preflight',{docs:[...context.docs],moduleScope:[...context.moduleScope],conflictPolicy:context.conflictPolicy,localMaskTransfer:context.moduleScope.includes(LOCAL_GRADE_OP)?context.localMaskTransfer:undefined,referenceColor:context.referenceColor,peopleTransfer:context.peopleTransfer});
  }
  async function commit(spillReviewAck?:SpillTransferAck[],shadowReviewAck?:ShadowTransferAck[]){
    if(state.phase!=='review'||!state.plan||state.plan.ok<1)return;
    if(state.plan.policy==='recheck'&&state.plan.blocked>0){set({message:'有受阻目标，请重新预检或修改选择'});return;}
    const spill=state.plan.module_scope.includes(SPILL_OP),targets=state.plan.targets.filter(target=>!target.blocked);
    if(spill&&(targets.some(target=>!validSpillTransfer(target.spill_transfer,target.document_id,target.revision,state.plan!.applies[SPILL_OP],target.source_proof))
      ||!validSpillTransferAck(spillReviewAck,targets.map(target=>target.spill_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标的祛反光前后预览。'});return;
    }
    const shadow=state.plan.module_scope.includes(SHADOW_OP);
    if(shadow&&(spill||targets.some(target=>!validShadowTransfer(target.shadow_transfer,target.document_id,target.revision,state.plan!.applies[SHADOW_OP],target.source_proof))
      ||!validShadowTransferAck(shadowReviewAck,targets.map(target=>target.shadow_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标的原图阴影前后预览。'});return;
    }
    await submit('commit',{preflightToken:state.plan.preflight_token,...(spill?{spillReviewAck:spillReviewAck!.map(ack=>({...ack}))}:{}),...(shadow?{shadowReviewAck:shadowReviewAck!.map(ack=>({...ack}))}:{})});
  }
  async function undo(batchId:string){
    if(state.phase==='uncertain'){set({hidden:false});return;}
    if(disposed||!batchId||['committing','preflighting'].includes(state.phase))return;
    set({plan:null,result:null,scopeLabel:''});await submit('undo',{batchId});
  }
  async function redo(batchId:string){
    if(state.phase==='uncertain'){set({hidden:false});return;}
    if(disposed||!batchId||['committing','preflighting'].includes(state.phase))return;
    set({plan:null,result:null,scopeLabel:''});await submit('redo',{batchId});
  }
  async function query(){
    if(state.phase!=='uncertain'||!pending)return;
    set({phase:pending.action==='preflight'?'preflighting':'committing',hidden:false,message:''});await poll(pending);
  }
  function acknowledgeInspection(){
    if(state.phase!=='uncertain')return;
    generation++;pending=null;set({phase:'closed',hidden:false,result:null,plan:null,message:''});
  }
  return {updateContext,start,commit,undo,redo,query,close,acknowledgeInspection,snapshot:()=>state,dispose:()=>{disposed=true;generation++;pending=null;}};
}
