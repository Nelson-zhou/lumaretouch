import {COLLARBONE_TRANSFER_OP as COLLARBONE_OP,COLLARBONE_VISUAL_LIMITS,validCollarboneVisual,validCollarboneAck,sameCollarboneAck,type CollarboneAck} from '../collarbone/transferModel';
import {sameAssociationReview,validAssociationReview,type AssociationReview,type AssociationTarget} from '../people/associationProof';
import {CROP_OP,CROP_LIMITS,sourceProof,validCropReview,type CropReview} from '../cropTransfer/model.ts';
import {samePeopleRequest,validPeopleReview,peopleProofDocument,type PeopleTransferRequest,type PeopleTransferProof,type PeopleTransferReview} from '../people/transferProof.ts';
import {validReferenceReview,type ReferenceReview} from '../referenceColor/ReferenceColorReview';
import {OPTICS_AUTO_OP,validOpticalReview,type OpticalTargetReview} from '../optics/transferReviewModel';
import {LOCAL_GRADE_OP,validTransferEvidence,sameTransferOptions,type MaskTransferOptions,type MaskTransferEvidence} from '../localMasks/transferModel.ts';
import {SPILL_TRANSFER_OP as SPILL_OP,SPILL_TRANSFER_LIMITS,spillTransferParameters,validSpillTransfer,validSpillTransferAck,type SpillTransferEvidence,type SpillTransferAck} from '../spillRemoval/transferModel.ts';
import {SHADOW_TRANSFER_OP as SHADOW_OP,SHADOW_TRANSFER_LIMITS,shadowTransferParameters,validShadowTransfer,validShadowTransferAck,type ShadowTransferEvidence,type ShadowTransferAck} from '../originalShadow/transferModel.ts';
import {TORSO_TRANSFER_OP as TORSO_OP,TORSO_TRANSFER_LIMITS,torsoTransferParameters,validTorsoTransfer,validTorsoTransferAck,sameTorsoTransferAck,type TorsoTransferEvidence,type TorsoTransferAck} from '../torsoLength/transferModel.ts';
import {WAIST_TRANSFER_OP as WAIST_OP,WAIST_TRANSFER_LIMITS,waistTransferParameters,validWaistTransfer,validWaistTransferAck,sameWaistTransferAck,type WaistTransferEvidence,type WaistTransferAck} from '../waistLength/transferModel.ts';
import {HEAD_TRANSFER_OP as HEAD_OP,HEAD_TRANSFER_LIMITS,headTransferParameters,validHeadTransfer,validHeadTransferAck,sameHeadTransferAck,type HeadTransferEvidence,type HeadTransferAck} from '../headSize/transferModel.ts';
import {bodyScalarNoWriteRejection,validBodyScalarReceiptState} from '../bodyScalar/transferModel.ts';
import {spillRevision} from '../spillRemoval/model.ts';
/** Reviewed batch lifecycle. A queued command is not evidence of successful edits. */
export type BatchAction='preflight'|'commit'|'undo'|'redo';
export type BatchOptions={docs?:string[];moduleScope?:string[];conflictPolicy?:string;batchId?:string;preflightToken?:string;requestId?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest;spillReviewAck?:SpillTransferAck[];shadowReviewAck?:ShadowTransferAck[];torsoReviewAck?:TorsoTransferAck[];waistReviewAck?:WaistTransferAck[];headReviewAck?:HeadTransferAck[];collarboneReviewAck?:CollarboneAck[]};
export type BatchTarget={index:number|null;reviewed_index?:number;path:string;document_id:string;revision?:string;blocked?:string|null;
  source_proof?:unknown;expected_revision?:string;current_revision?:string|null;result_revision?:string|null;outcome?:string;before?:unknown;spill_transfer?:SpillTransferEvidence;shadow_transfer?:ShadowTransferEvidence;torso_transfer?:TorsoTransferEvidence;waist_transfer?:WaistTransferEvidence;head_transfer?:HeadTransferEvidence;crop_transfer?:CropReview;local_mask_transfer?:MaskTransferEvidence;optical_transfer?:OpticalTargetReview;reference_color?:ReferenceReview;people_transfer?:PeopleTransferReview|null;association?:AssociationTarget['association']};
type BatchSource={document_id:string;revision:string;path:string;source_proof?:unknown};
export type BatchReply={batch_id?:string;request_id:string;action:BatchAction;success:boolean;error?:string;outcome_unknown?:boolean;
  torso_review_ack?:TorsoTransferAck[];
  waist_review_ack?:WaistTransferAck[];
  head_review_ack?:HeadTransferAck[];collarbone_review_ack?:CollarboneAck[];
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
  let pending:{id:string;action:BatchAction;generation:number;contextKey:string;token?:string;scope?:string[];policy?:string;transfer?:MaskTransferOptions;reference?:{strength:number};people?:PeopleTransferRequest;peopleProof?:PeopleTransferProof;referencePath?:string;docs?:string[];torsoAck?:TorsoTransferAck[];waistAck?:WaistTransferAck[];headAck?:HeadTransferAck[];collarboneAck?:CollarboneAck[]}|null=null;
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
    const collarbone=scope.includes(COLLARBONE_OP);
    if(collarbone&&(!people||people.target_policy==='persistent_association'||result.targets.length>COLLARBONE_VISUAL_LIMITS.targets))throw Error('锁骨逐图审核仅支持当前明确人物目标迁移，每批最多 16 张。');
    const spill=scope.includes(SPILL_OP);
    if(spill&&(scope.includes('lnx.id_background.v1')||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!spillTransferParameters(result.applies[SPILL_OP])))throw Error('祛反光预检缺少真实源图证明或包含非标量参数');
    if(spill&&result.targets.length>SPILL_TRANSFER_LIMITS.targets)throw Error('祛反光审核最多同时选择 8 张目标，不能省略逐图审核');
    const shadow=scope.includes(SHADOW_OP);
    if(shadow&&((scope.includes('lnx.id_background.v1')||scope.includes(SPILL_OP))||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!shadowTransferParameters(result.applies[SHADOW_OP])))throw Error('原图阴影预检缺少真实源图证明或包含非标量参数');
    if(shadow&&result.targets.length>SHADOW_TRANSFER_LIMITS.targets)throw Error('原图阴影审核最多同时选择 8 张目标，不能省略逐图审核');
    const torso=scope.includes(TORSO_OP);
    if(torso&&(scope.length!==1||people||result.people_transfer||result.persistent_association||result.association_source
      ||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!torsoTransferParameters(result.applies[TORSO_OP])))throw Error('上身长度必须单独审核源标量，不自动建立或复制身体归属');
    if(torso&&result.targets.length>TORSO_TRANSFER_LIMITS.targets)throw Error('上身长度审核每批最多 8 张目标，不能省略逐图审核');
    const waist=scope.includes(WAIST_OP);
    if(waist&&(scope.length!==1||people||transfer||reference||result.people_transfer||result.local_mask_transfer||result.persistent_association||result.association_source
      ||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)
      ||!waistTransferParameters(result.applies[WAIST_OP])))throw Error('腰长必须单独审核源标量，不自动建立或复制身体、腰部标记或归属');
    if(waist&&result.targets.length>WAIST_TRANSFER_LIMITS.targets)throw Error('腰长审核每批最多 8 张目标，不能省略逐图审核');
    const head=scope.includes(HEAD_OP);
    if(head&&(scope.length!==1||people||transfer||reference||result.people_transfer||result.local_mask_transfer||result.persistent_association||result.association_source
      ||result.source_snapshot.document_id!==context.sourceDocumentId||!sourceProof(result.source_snapshot.source_proof)||!spillRevision(result.source_snapshot.revision)
      ||!headTransferParameters(result.applies[HEAD_OP])))throw Error('小头必须单独审核源标量，不自动建立或复制身体、完整头发/头部框、缩小中心及过渡框或归属');
    if(head&&result.targets.length>HEAD_TRANSFER_LIMITS.targets)throw Error('小头审核每批最多 8 张目标，不能省略逐图审核');
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
    const ids=new Set<string>(),indices=new Set<number>();let blocked=0;
    for(const item of result.targets){const t=item as BatchTarget;
      if(!t||typeof t.path!=='string'||!identity(t.document_id)||!revision(t.revision)
        ||!Number.isInteger(t.index)||(t.index??-1)<0||ids.has(t.document_id))throw Error('预检目标身份不完整');
      if(waist||head){if(indices.has(t.index!))throw Error('身体标量预检不能重复同一目标行');indices.add(t.index!);}
      if(head&&(!Number.isSafeInteger(t.index)||!spillRevision(t.revision)))throw Error('小头目标行或冻结版本必须能准确标识，不能舍入或改写');
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
      if(torso&&t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked))throw Error('上身长度目标受阻状态无效');
      if((!torso||t.blocked)&&t.torso_transfer!=null)throw Error('受阻或未请求的目标不能提供上身长度审核证据');
      if(torso&&!t.blocked){
        const before=object(t.before)?t.before[TORSO_OP]:null;
        if(!sourceProof(t.source_proof)||!object(before)||Object.keys(before).length!==1||!hash(before.target_recipe_key)
          ||t.document_id===result.source_snapshot.document_id&&!sameSourceProof(t.source_proof,result.source_snapshot.source_proof))throw Error('上身长度目标缺少独立来源和冻结身体依赖');
        if(!validTorsoTransfer(t.torso_transfer,t.document_id,t.revision,result.applies[TORSO_OP],t.source_proof))throw Error('上身长度目标缺少实际身体、本人面部、独立支持审核或真实前后预览');
      }
      if(waist&&t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked))throw Error('腰长目标受阻状态无效');
      if((!waist||t.blocked)&&t.waist_transfer!=null)throw Error('受阻或未请求的目标不能提供腰长审核证据');
      if(waist&&(t.head_transfer!=null||t.torso_transfer!=null||t.spill_transfer!=null||t.shadow_transfer!=null||t.people_transfer!=null||t.local_mask_transfer!=null||t.reference_color!=null||t.optical_transfer!=null||t.crop_transfer!=null))throw Error('腰长不能混用其他作用域的目标审核');
      if(waist&&!t.blocked){
        const before=object(t.before)?t.before[WAIST_OP]:null;
        if(!sourceProof(t.source_proof)||!object(t.before)||Object.keys(t.before).length!==1||!object(before)||Object.keys(before).length!==1||!hash(before.target_recipe_key)
          ||t.document_id===result.source_snapshot.document_id&&(!sameSourceProof(t.source_proof,result.source_snapshot.source_proof)||t.revision!==result.source_snapshot.revision))throw Error('腰长目标缺少独立来源和冻结腰部依赖');
        if(!validWaistTransfer(t.waist_transfer,t.document_id,t.revision,result.applies[WAIST_OP],t.source_proof))throw Error('腰长目标缺少实际身体、本人面部、腰部独立支持审核或真实前后预览');
      }
      if(head&&t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked))throw Error('小头目标受阻状态无效');
      if((!head||t.blocked)&&t.head_transfer!=null)throw Error('受阻或未请求的目标不能提供小头审核证据');
      if(head&&(t.waist_transfer!=null||t.torso_transfer!=null||t.spill_transfer!=null||t.shadow_transfer!=null||t.people_transfer!=null||t.local_mask_transfer!=null||t.reference_color!=null||t.optical_transfer!=null||t.crop_transfer!=null))throw Error('小头不能混用其他作用域的目标审核');
      if(head&&!t.blocked){
        const before=object(t.before)?t.before[HEAD_OP]:null;
        if(!sourceProof(t.source_proof)||!object(t.before)||Object.keys(t.before).length!==1||!object(before)||Object.keys(before).length!==1||!hash(before.target_recipe_key)
          ||t.document_id===result.source_snapshot.document_id&&(!sameSourceProof(t.source_proof,result.source_snapshot.source_proof)||t.revision!==result.source_snapshot.revision))throw Error('小头目标缺少独立来源和冻结头部依赖');
        if(!validHeadTransfer(t.head_transfer,t.document_id,t.revision,result.applies[HEAD_OP],t.source_proof))throw Error('小头目标缺少实际身体、本人面部、完整头部独立支持审核或真实前后预览');
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
    const head=plan.module_scope.includes(HEAD_OP);
    if(head&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||result.batch_id.length>128||/[\u0000-\u001f\u007f]/.test(result.batch_id)
      ||!Array.isArray(result.targets)))throw Error('小头提交缺少可追溯的批次身份或实际应用行清单');
    if(plan.module_scope.includes(SPILL_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('祛反光提交来源证明与冻结预检不同');
    if(plan.module_scope.includes(SHADOW_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('原图阴影提交来源证明与冻结预检不同');
    if(plan.module_scope.includes(TORSO_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('上身长度提交来源证明与冻结预检不同');
    if(plan.module_scope.includes(WAIST_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('腰长提交来源证明与冻结预检不同');
    if(plan.module_scope.includes(HEAD_OP)&&!sameSourceProof(result.source_snapshot?.source_proof,plan.source_snapshot.source_proof))throw Error('小头提交来源证明与冻结预检不同');
    if(plan.persistent_association){const source=result.source_outcome,before=plan.association_source;
      if(!sameAssociationReview(result.persistent_association,plan.persistent_association))throw Error('持久关联提交内容或版本与冻结审核不同');
      if(!source||!before||source.document_id!==before.document_id||source.path!==before.path||source.expected_revision!==before.revision||source.outcome!=='applied'||!revision(source.result_revision)||BigInt(source.result_revision)<=BigInt(before.revision??'0'))throw Error('持久关联缺少源成员的实际提交结果');}
    const reviewed=new Map(plan.targets.map(t=>[t.document_id,t])),appliedIndices=new Set<number>();
    for(const target of result.target_outcomes){
      const before=reviewed.get(target.document_id);
      if(!before||target.expected_revision!==before.revision||target.path!==before.path
        ||!['applied','skipped'].includes(target.outcome??''))throw Error('提交结果与预检目标不一致');
      if(head&&([target.head_transfer,target.waist_transfer,target.torso_transfer,target.spill_transfer,target.shadow_transfer,
        target.people_transfer,target.local_mask_transfer,target.reference_color,target.optical_transfer,target.crop_transfer].some(value=>value!=null)
        ||Object.hasOwn(target,'head_review_ack')||target.outcome==='applied'&&(before.blocked!=null||target.blocked!=null||target.current_revision!==before.revision)))throw Error('小头提交混入了未审核证据、受阻目标或不一致的当前版本');
      if(plan.module_scope.includes(WAIST_OP)||plan.module_scope.includes(HEAD_OP)){
        // A project row may relocate while retaining its exact document/path.
        // The frozen index is echoed separately from the current applied index.
        if(target.reviewed_index!==before.index||target.outcome==='applied'&&(!Number.isSafeInteger(target.index)||(target.index??-1)<0
          ||appliedIndices.has(target.index!)||!revision(target.result_revision)||plan.module_scope.includes(HEAD_OP)&&!spillRevision(target.result_revision)
          ||BigInt(target.result_revision)<=BigInt(before.revision??'0')))throw Error('身体标量提交目标行或实际前进版本与冻结审核不一致');
        if(target.outcome==='applied')appliedIndices.add(target.index!);
      }
      if(plan.persistent_association&&(target.outcome!=='applied'||!revision(target.result_revision)||BigInt(target.result_revision)<=BigInt(before.revision??'0')))throw Error('持久关联成员未全部提交，结果需要检查');
      reviewed.delete(target.document_id);
    }
    if(head&&JSON.stringify(result.targets)!==JSON.stringify(result.target_outcomes.filter(target=>target.outcome==='applied').map(target=>target.index)))throw Error('小头实际应用行清单与逐图终态不一致');
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
          if(request.waistAck!==undefined&&(typeof result.outcome_unknown!=='boolean'||result.success&&result.outcome_unknown))throw Error('腰长提交结果缺少明确且一致的终态');
          if(result.waist_review_ack!==undefined&&(request.action!=='commit'||request.waistAck===undefined))throw Error('未请求的腰长逐图确认回执');
          if(request.action==='commit'&&request.waistAck!==undefined&&!bodyScalarNoWriteRejection(result,request.token)
            &&(result.module_scope?.length!==1||result.module_scope[0]!==WAIST_OP||result.preflight_token!==request.token
              ||!sameWaistTransferAck(result.waist_review_ack,request.waistAck)))throw Error('腰长提交回执与原请求、冻结令牌或有序 PNG 对确认不一致');
          if((request.headAck!==undefined||request.scope?.includes(HEAD_OP)||result.module_scope?.includes(HEAD_OP))
            &&!validBodyScalarReceiptState(result))throw Error('小头提交结果缺少明确且一致的终态');
          if(result.head_review_ack!==undefined&&(request.action!=='commit'||request.headAck===undefined))throw Error('未请求的小头逐图确认回执');
          if(request.action==='commit'&&request.headAck!==undefined&&!bodyScalarNoWriteRejection(result,request.token)
            &&(result.module_scope?.length!==1||result.module_scope[0]!==HEAD_OP||result.preflight_token!==request.token
              ||!sameHeadTransferAck(result.head_review_ack,request.headAck)))throw Error('小头提交回执与原请求、冻结令牌或有序 PNG 对确认不一致');
          if(result.collarbone_review_ack!==undefined&&(request.action!=='commit'||request.collarboneAck===undefined))throw Error('未请求的锁骨逐图确认回执');
          if(request.collarboneAck!==undefined&&(!validBodyScalarReceiptState(result)||!bodyScalarNoWriteRejection(result,request.token)&&(result.preflight_token!==request.token||!result.module_scope?.includes(COLLARBONE_OP)||!sameCollarboneAck(result.collarbone_review_ack,request.collarboneAck))))throw Error('锁骨终态或逐图确认回执不匹配，只能查询原请求');
          if(result.torso_review_ack!==undefined&&(request.action!=='commit'||result.module_scope?.length!==1||result.module_scope[0]!==TORSO_OP||result.preflight_token!==request.token||!sameTorsoTransferAck(result.torso_review_ack,request.torsoAck)))throw Error('上身长度提交回执与本次逐图确认不一致');
          if(request.action==='commit'&&request.torsoAck!==undefined&&result.success&&!sameTorsoTransferAck(result.torso_review_ack,request.torsoAck))throw Error('缺少上身长度 PNG 对确认的终态回执');
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
    const request={id,action,generation:g,contextKey:key,token:opts.preflightToken,scope:opts.moduleScope,policy:opts.conflictPolicy,transfer:opts.localMaskTransfer,reference:opts.referenceColor,people:opts.peopleTransfer,peopleProof:context.peopleProof,referencePath:context.referencePath,docs:opts.docs,torsoAck:opts.torsoReviewAck?.map(ack=>({...ack})),waistAck:opts.waistReviewAck?.map(ack=>({...ack})),headAck:opts.headReviewAck?.map(ack=>({...ack})),collarboneAck:opts.collarboneReviewAck?.map(ack=>({...ack}))};pending=request;
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
    if(context.moduleScope.includes(TORSO_OP)&&(context.moduleScope.length!==1||context.peopleTransfer)){set({phase:'error',plan:null,result:null,message:'上身长度必须单独同步，不自动关联身体或混入人物配对。'});return;}
    if(context.moduleScope.includes(TORSO_OP)&&context.docs.length>TORSO_TRANSFER_LIMITS.targets){set({phase:'error',plan:null,result:null,message:'上身长度审核每批最多 8 张目标，请减少选择；不会只审核前几张。'});return;}
    if(context.moduleScope.includes(WAIST_OP)&&(context.moduleScope.length!==1||context.peopleTransfer||context.referenceColor)){set({phase:'error',plan:null,result:null,message:'腰长必须单独同步，不自动关联身体或混入其他审核。'});return;}
    if(context.moduleScope.includes(HEAD_OP)&&(context.moduleScope.length!==1||context.peopleTransfer||context.referenceColor)){set({phase:'error',plan:null,result:null,message:'小头必须单独同步，不自动关联身体或混入其他审核。'});return;}
    if(context.moduleScope.includes(WAIST_OP)&&context.docs.length>WAIST_TRANSFER_LIMITS.targets){set({phase:'error',plan:null,result:null,message:'腰长审核每批最多 8 张目标，请减少选择；不会只审核前几张。'});return;}
    if(context.moduleScope.includes(HEAD_OP)&&context.docs.length>HEAD_TRANSFER_LIMITS.targets){set({phase:'error',plan:null,result:null,message:'小头审核每批最多 8 张目标，请减少选择；不会只审核前几张。'});return;}
    if(context.moduleScope.includes(SHADOW_OP)&&context.moduleScope.some(op=>[SPILL_OP,'lnx.id_background.v1'].includes(op))){set({phase:'error',plan:null,result:null,message:'原图阴影标量不能与祛染或整套背景一起同步，请分别预检并审核。'});return;}
    set({plan:null,result:null,scopeLabel:context.label});
    await submit('preflight',{docs:[...context.docs],moduleScope:[...context.moduleScope],conflictPolicy:context.conflictPolicy,localMaskTransfer:context.moduleScope.includes(LOCAL_GRADE_OP)?context.localMaskTransfer:undefined,referenceColor:context.referenceColor,peopleTransfer:context.peopleTransfer});
  }
  async function commit(spillReviewAck?:SpillTransferAck[],shadowReviewAck?:ShadowTransferAck[],torsoReviewAck?:TorsoTransferAck[],waistReviewAck?:WaistTransferAck[],headReviewAck?:HeadTransferAck[],collarboneReviewAck?:CollarboneAck[]){
    if(state.phase!=='review'||!state.plan||state.plan.ok<1)return;
    if(state.plan.policy==='recheck'&&state.plan.blocked>0){set({message:'有受阻目标，请重新预检或修改选择'});return;}
    const collarbone=state.plan.module_scope.includes(COLLARBONE_OP);
    const spill=state.plan.module_scope.includes(SPILL_OP),targets=state.plan.targets.filter(target=>!target.blocked);
    if(collarbone&&(targets.some(t=>!t.people_transfer||!validCollarboneVisual(t.people_transfer.collarbone_visual,t.people_transfer))||!validCollarboneAck(collarboneReviewAck,targets.map(t=>t.people_transfer!.collarbone_visual!)))){set({message:'请逐图查看并确认所有目标的真实锁骨前后效果，包括归零。'});return;}
    if(!collarbone&&collarboneReviewAck!==undefined){set({message:'锁骨确认不属于当前冻结范围。'});return;}
    if(spill&&(targets.some(target=>!validSpillTransfer(target.spill_transfer,target.document_id,target.revision,state.plan!.applies[SPILL_OP],target.source_proof))
      ||!validSpillTransferAck(spillReviewAck,targets.map(target=>target.spill_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标的祛反光前后预览。'});return;
    }
    const shadow=state.plan.module_scope.includes(SHADOW_OP);
    if(shadow&&(spill||targets.some(target=>!validShadowTransfer(target.shadow_transfer,target.document_id,target.revision,state.plan!.applies[SHADOW_OP],target.source_proof))
      ||!validShadowTransferAck(shadowReviewAck,targets.map(target=>target.shadow_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标的原图阴影前后预览。'});return;
    }
    const torso=state.plan.module_scope.includes(TORSO_OP);
    if(torso&&(state.plan.module_scope.length!==1||spillReviewAck!==undefined||shadowReviewAck!==undefined||waistReviewAck!==undefined||headReviewAck!==undefined
      ||targets.some(target=>!validTorsoTransfer(target.torso_transfer,target.document_id,target.revision,state.plan!.applies[TORSO_OP],target.source_proof))
      ||!validTorsoTransferAck(torsoReviewAck,targets.map(target=>target.torso_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标的身体及本人面部前后效果，不接受通用或源图确认。'});return;
    }
    if(!torso&&torsoReviewAck!==undefined){set({message:'上身长度确认不属于当前冻结范围。'});return;}
    const waist=state.plan.module_scope.includes(WAIST_OP);
    if(waist&&(state.plan.module_scope.length!==1||spillReviewAck!==undefined||shadowReviewAck!==undefined||torsoReviewAck!==undefined||headReviewAck!==undefined
      ||targets.some(target=>!validWaistTransfer(target.waist_transfer,target.document_id,target.revision,state.plan!.applies[WAIST_OP],target.source_proof))
      ||!validWaistTransferAck(waistReviewAck,targets.map(target=>target.waist_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标身体及本人面部的腰长前后效果，不接受上身长度或源图确认。'});return;
    }
    if(!waist&&waistReviewAck!==undefined){set({message:'腰长确认不属于当前冻结范围。'});return;}
    const head=state.plan.module_scope.includes(HEAD_OP);
    if(head&&(state.plan.module_scope.length!==1||spillReviewAck!==undefined||shadowReviewAck!==undefined||waistReviewAck!==undefined||torsoReviewAck!==undefined
      ||targets.some(target=>!validHeadTransfer(target.head_transfer,target.document_id,target.revision,state.plan!.applies[HEAD_OP],target.source_proof))
      ||!validHeadTransferAck(headReviewAck,targets.map(target=>target.head_transfer!)))){
      set({message:'请先逐张查看并确认所有可同步目标身体及本人面部的小头前后效果，不接受上身长度或源图确认。'});return;
    }
    if(!head&&headReviewAck!==undefined){set({message:'小头确认不属于当前冻结范围。'});return;}
    await submit('commit',{preflightToken:state.plan.preflight_token,...(spill?{spillReviewAck:spillReviewAck!.map(ack=>({...ack}))}:{}),...(shadow?{shadowReviewAck:shadowReviewAck!.map(ack=>({...ack}))}:{}),...(torso?{torsoReviewAck:torsoReviewAck!.map(ack=>({...ack}))}:{}),...(waist?{waistReviewAck:waistReviewAck!.map(ack=>({...ack}))}:{}),...(head?{headReviewAck:headReviewAck!.map(ack=>({...ack}))}:{}),...(collarbone?{collarboneReviewAck:collarboneReviewAck!.map(ack=>({...ack}))}:{})});
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
    if(pending?.waistAck!==undefined){set({message:'腰长提交结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    if(pending?.headAck!==undefined){set({message:'小头提交结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    if(pending?.collarboneAck!==undefined){set({message:'锁骨同步结果尚未确定，只能查询原请求，不能释放后重复提交。'});return;}
    generation++;pending=null;set({phase:'closed',hidden:false,result:null,plan:null,message:''});
  }
  return {updateContext,start,commit,undo,redo,query,close,acknowledgeInspection,snapshot:()=>state,dispose:()=>{disposed=true;generation++;pending=null;}};
}
