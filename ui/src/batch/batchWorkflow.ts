import {decorationMultiHistory,registerDecorationMultiHistory,type DecorationHistoryField} from '../faceDecoration/multiHistory';
import {validDecorationCohort,decorationCohortAckDigest,decorationCohortTargets,decorationCohortAck,sameDecorationCohortAck} from '../faceDecoration/cohortModel';
import {decorationBatchHistoryClass,registerDecorationBatchReceipt,validDecorationBatchMarker,type DecorationBatchMarker} from '../faceDecoration/batchHistoryRegistry';
import {OP as DECORATION_OP,validDecorationEvidence,sameDecorationRender,decorationAck,sameDecorationAck,verifyDecorationCoverage,type DecorationAck} from '../faceDecoration/transferModel';
import {eyeBagPresetAliasHistoryClass,eyeBagPresetAliasWritePending,eyeBagPresetAliasWorkspace,subscribeEyeBagPresetAliasWorkspace,sameEyeBagPresetAliasMarker,type EyeBagPresetAliasMarker} from '../eyeBagPreserve/presetAliasHistoryRegistry';
import {recoveryAliasHistoryClass,recoveryAliasWritePending,recoveryAliasWorkspace,subscribeRecoveryAliasWorkspace,sameRecoveryAliasMarker,type RecoveryAliasMarker} from '../effectRecovery/aliasHistoryRegistry';
import {eyeBagAliasHistoryClass, registerEyeBagAliasReceipt} from '../eyeBagPreserve/aliasHistoryRegistry';
import type {EyeBagAliasCommit} from '../eyeBagPreserve/model';
import {eyeBagCohortHistoryClass, registerEyeBagCohortReceipt} from '../eyeBagPreserve/cohortHistoryRegistry';
import {checkEyeBagCohortReceipt, checkEyeBagCohortCommit} from '../eyeBagPreserve/cohortReceipt';
import {validEyeBagCohort, eyeBagCohortTargets, validEyeBagCohortAck, verifyEyeBagCohortCoverage, type EyeBagCohortAck} from '../eyeBagPreserve/cohortModel';
import {eyeBagBatchHistoryClass, registerEyeBagBatchReceipt} from '../eyeBagPreserve/batchHistoryRegistry';
import {EYE_BAG_BATCH_OP, EYE_BAG_BATCH_LIMIT, validEyeBagBatchReview, validEyeBagBatchAck, sameEyeBagBatchAck, verifyEyeBagBatchCoverage, type EyeBagBatchAck} from '../eyeBagPreserve/batchModel';
import {validPortraitCohort,portraitCohortTargets,validPortraitCohortAck,samePortraitCohortAck,type PortraitCohortAck} from '../portraitCohort/model';
import {validCollarboneCohort,collarbonePlanTargets} from '../collarbone/cohortModel';
import {COLLARBONE_TRANSFER_OP as COLLARBONE_OP,COLLARBONE_VISUAL_LIMITS,validCollarboneVisual,validCollarboneAck,sameCollarboneAck,type CollarboneAck} from '../collarbone/transferModel';
import {sameAssociationReview,validAssociationReview,type AssociationRequest,type AssociationReview,type AssociationTarget} from '../people/associationProof';
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
import {validFaceStyleRecipe, type FaceStyleAliasCommit} from '../faceStyle/model';
import {faceStyleAliasHistoryClass, registerFaceStyleAliasReceipt} from '../faceStyle/aliasHistoryRegistry';
import {FACE_STYLE_BATCH_LIMIT, faceStyleSelection, sameFaceStyleRecipe, validFaceStyleBatchVisual,
  validFaceStyleBatchAck, sameFaceStyleBatchAck, verifyFaceStyleBatchRecipe, type FaceStyleBatchAck} from '../faceStyle/batchModel';
/** Reviewed batch lifecycle. A queued command is not evidence of successful edits. */
export type BatchAction='preflight'|'commit'|'undo'|'redo';
export type BatchOptions={docs?:string[];moduleScope?:string[];conflictPolicy?:string;batchId?:string;preflightToken?:string;requestId?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest;spillReviewAck?:SpillTransferAck[];shadowReviewAck?:ShadowTransferAck[];torsoReviewAck?:TorsoTransferAck[];waistReviewAck?:WaistTransferAck[];headReviewAck?:HeadTransferAck[];faceDecorationCohortAck?:DecorationAck[];faceDecorationReviewAck?:DecorationAck[];collarboneReviewAck?:CollarboneAck[];faceStyleReviewAck?:FaceStyleBatchAck[];portraitCohortAck?:PortraitCohortAck[];eyeBagReviewAck?:EyeBagBatchAck[];eyeBagCohortAck?:EyeBagCohortAck[]};
export type BatchTarget={index:number|null;reviewed_index?:number;path:string;document_id:string;revision?:string;blocked?:string|null;
  source_proof?:unknown;expected_revision?:string;current_revision?:string|null;result_revision?:string|null;outcome?:string;before?:unknown;spill_transfer?:SpillTransferEvidence;shadow_transfer?:ShadowTransferEvidence;torso_transfer?:TorsoTransferEvidence;waist_transfer?:WaistTransferEvidence;head_transfer?:HeadTransferEvidence;crop_transfer?:CropReview;local_mask_transfer?:MaskTransferEvidence;optical_transfer?:OpticalTargetReview;reference_color?:ReferenceReview;people_transfer?:PeopleTransferReview|null;association?:AssociationTarget['association']};
type BatchSource={document_id:string;revision:string;path:string;source_proof?:unknown};
export type BatchReply={face_decoration_cohort?:boolean;face_decoration_cohort_ack?:DecorationAck[];face_decoration_cohort_review?:DecorationBatchMarker;face_decoration_alias_review?:DecorationBatchMarker;face_decoration_batch_review?:DecorationBatchMarker;face_decoration_visual_required?:boolean;face_decoration_review_ack?:DecorationAck[];eye_bag_recovery_alias_review?:RecoveryAliasMarker;eye_bag_preset_alias_review?:EyeBagPresetAliasMarker;batch_id?:string|null;request_id:string;action:BatchAction;success:boolean;error?:string;outcome_unknown?:boolean;no_write?:boolean;rolled_back?:boolean;
  eye_bag_review_ack?:EyeBagBatchAck[];eye_bag_cohort?:boolean;eye_bag_cohort_ack?:EyeBagCohortAck[];
  torso_review_ack?:TorsoTransferAck[];
  waist_review_ack?:WaistTransferAck[];
  head_review_ack?:HeadTransferAck[];collarbone_review_ack?:CollarboneAck[];collarbone_cohort?:boolean;
  face_style_review_ack?:FaceStyleBatchAck[];portrait_cohort_ack?:PortraitCohortAck[];portrait_cohort?:boolean;
  persistent_association?:AssociationReview;association_source?:BatchTarget;source_outcome?:BatchTarget;people_transfer?:boolean;local_mask_transfer?:MaskTransferOptions;preflight_token?:string;source_snapshot?:BatchSource;source_changed_since_preflight?:boolean;
  module_scope?:string[];applies?:Record<string,unknown>;policy?:string;targets?:unknown[];target_outcomes?:BatchTarget[];
  rejected_docs?:Array<{doc:unknown;error:string}>;ok?:number;blocked?:number;restored?:number[];conflicts?:Array<{path:string;reason:string}>};
export type BatchPlan=Omit<BatchReply,'targets'|'success'|'preflight_token'|'source_snapshot'|'module_scope'|'applies'|'ok'|'blocked'>&{success:true;preflight_token:string;source_snapshot:BatchSource;
  module_scope:string[];targets:BatchTarget[];applies:Record<string,unknown>;ok:number;blocked:number};
export type BatchContext={reviewEpoch?:number;docs:string[];moduleScope:string[];conflictPolicy:string;sourceDocumentId:string;enabled:boolean;label:string;referencePath?:string;localMaskTransfer?:MaskTransferOptions;referenceColor?:{strength:number};peopleTransfer?:PeopleTransferRequest;peopleProof?:PeopleTransferProof};
export type BatchUi={phase:'closed'|'preflighting'|'review'|'committing'|'uncertain'|'done'|'error';
  hidden?:boolean;queryOnly?:boolean;operation:BatchAction;plan:BatchPlan|null;result:BatchReply|null;message:string;scopeLabel:string};
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
  let key='',generation=0,contextRevision=0,disposed=false;
  const faceStyleBatchIds=new Set<string>(),portraitCohortBatchIds=new Set<string>(),eyeBagBatchIds=new Map<string,number>();
  let pending:{id:string;action:BatchAction;generation:number;contextKey:string;contextRevision:number;batchId?:string;aliasMemberCount?:number|null;token?:string;scope?:string[];policy?:string;transfer?:MaskTransferOptions;reference?:{strength:number};people?:PeopleTransferRequest;peopleProof?:PeopleTransferProof;referencePath?:string;docs?:string[];torsoAck?:TorsoTransferAck[];waistAck?:WaistTransferAck[];headAck?:HeadTransferAck[];decorationCohortAck?:DecorationAck[];decorationHistoryField?:DecorationHistoryField;decorationWrite?:boolean;decorationReviewSha?:string|null;decorationMemberCount?:number|null;decorationAck?:DecorationAck[];collarboneAck?:CollarboneAck[];collarboneCohort?:boolean;faceStyleAck?:FaceStyleBatchAck[];faceStyleWrite?:boolean;portraitAck?:PortraitCohortAck[];portraitWrite?:boolean;eyeBagAck?:EyeBagBatchAck[];eyeBagCohortAck?:EyeBagCohortAck[];eyeBagWrite?:boolean;eyeBagMemberCount?:number|null;presetAliasWrite?:boolean;presetAliasEpoch?:string|null;presetAliasMarker?:EyeBagPresetAliasMarker|null;presetAliasMemberCount?:number|null;recoveryAliasWrite?:boolean;recoveryAliasEpoch?:string|null;recoveryAliasMarker?:RecoveryAliasMarker|null;recoveryAliasMemberCount?:number|null}|null=null;
  let state:BatchUi={phase:'closed',operation:'preflight',plan:null,result:null,message:'',scopeLabel:''};
  const set=(patch:Partial<BatchUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  const stopWorkspaceRecovery=subscribeEyeBagPresetAliasWorkspace(replacement=>{
    if(disposed||!pending?.presetAliasWrite||pending.presetAliasEpoch!==replacement.previous)return;
    generation++;pending=null;
    set({phase:'error',hidden:false,queryOnly:false,plan:null,result:null,message:'已确认进入新的项目工作区。原混合预设历史请求的结果仍未知，不认定撤销或重做成功；请核对全部成员后使用新工作区的准确批次台账。'});
  });
  const stopRecoveryWorkspace=subscribeRecoveryAliasWorkspace(replacement=>{
    if(disposed||!pending?.recoveryAliasWrite||pending.recoveryAliasEpoch!==replacement.previous)return;
    generation++;pending=null;
    set({phase:'error',hidden:false,queryOnly:false,plan:null,result:null,message:'已确认进入新的项目工作区。原共享来源恢复历史请求结果仍未知，不认定成功；请核对全部成员后使用新工作区的准确批次台账。'});
  });
  const active=(g:number)=>!disposed&&g===generation;
  function close(){
    if(state.phase==='committing')return;
    if(state.phase==='uncertain'){set({hidden:true});return;}
    generation++;pending=null;set({phase:'closed',hidden:false,queryOnly:false,plan:null,result:null,message:''});
  }
  function updateContext(next:BatchContext){
    const nextKey=JSON.stringify([next.docs,next.moduleScope,next.conflictPolicy,next.sourceDocumentId,next.enabled,next.localMaskTransfer,next.referenceColor,next.referencePath,next.peopleTransfer,next.peopleProof,next.reviewEpoch]);
    // An away/back transition must not revive an unknown read. Submitted writes keep their original identity.
    if(key!==nextKey){contextRevision++;if(['preflighting','review'].includes(state.phase))close();}
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
    const eyeBag=people?.target_policy==='explicit_face_map'&&people.eye_bag!==undefined;
    if(eyeBag&&(transfer!==undefined||reference!==undefined||result.targets.length>EYE_BAG_BATCH_LIMIT||!scope.includes(EYE_BAG_BATCH_OP)))throw Error('祛眼袋审核必须使用明确的独立目标、标量选择和逐目标旧版策略，每批最多 16 张。');
    if(result.eye_bag_review_ack!==undefined||result.eye_bag_cohort_ack!==undefined)throw Error('预检不能携带祛眼袋提交确认。');
    const decoration=result.face_decoration_visual_required===true;
    if(result.face_decoration_visual_required!==undefined&&!decoration||scope.includes(DECORATION_OP)&&!decoration&&result.face_decoration_cohort!==true||result.face_decoration_review_ack!==undefined)throw Error('装饰批次审核标记缺失或含未请求确认');
    if(decoration&&(!people||people.target_policy!=='explicit_face_map'||result.targets.length>16))throw Error('装饰完整审核仅支持最多 16 张明确配对目标');
    if(result.face_decoration_cohort===true&&decoration)throw Error('装饰关联不能伪装成仅目标普通批次');
    if(result.face_decoration_cohort_ack!==undefined)throw Error('预检不能携带装饰关联确认');
    if((result.face_decoration_cohort!==undefined||people?.target_policy==='persistent_association')&&(!people||people.target_policy!=='persistent_association'||!validDecorationCohort(result as BatchPlan,people)))throw Error('装饰关联缺少源成员及全部成员完整图像证明');
    const collarbone=scope.includes(COLLARBONE_OP);
    const faceStyle=people?.target_policy==='explicit_face_map'&&people.face_style!==undefined;
    if(faceStyle&&(transfer!==undefined||reference!==undefined||result.targets.length>FACE_STYLE_BATCH_LIMIT
      ||JSON.stringify(scope)!==JSON.stringify(Object.keys(faceStyleSelection()))))throw Error('新版脸型必须仅审核明确配对的完整 30 项配方，每批最多 16 张目标。');
    if(collarbone&&(!people||result.targets.length+(people.target_policy==='persistent_association'?1:0)>COLLARBONE_VISUAL_LIMITS.targets))throw Error('锁骨逐图审核仅支持当前明确人物目标迁移，每批最多 16 张。');
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
    if(people?.target_policy!=='persistent_association'&&(result.persistent_association||result.association_source||result.collarbone_cohort!==undefined||result.portrait_cohort!==undefined||result.portrait_cohort_ack!==undefined||result.eye_bag_cohort!==undefined||result.eye_bag_cohort_ack!==undefined))throw Error('未请求的持久关联回执');
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
      if(faceStyle&&(t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked)
        ||!!t.blocked&&t.people_transfer!=null
        ||[t.head_transfer,t.waist_transfer,t.torso_transfer,t.spill_transfer,t.shadow_transfer,t.crop_transfer,
          t.local_mask_transfer,t.optical_transfer,t.reference_color,t.association].some(value=>value!=null)))throw Error('新版脸型目标混入未请求的审核，或受阻目标伪造了可用证据');
      if(!eyeBag&&t.people_transfer&&['eye_bag','eye_bag_coverage','eye_bag_visual'].some(field=>Object.hasOwn(t.people_transfer!,field)))throw Error('未请求的祛眼袋目标审核。');
      if(eyeBag&&(t.blocked!=null&&(typeof t.blocked!=='string'||!t.blocked)||!!t.blocked&&t.people_transfer!=null))throw Error('受阻祛眼袋目标不能携带可提交审核证据。');
      if(!faceStyle&&t.people_transfer&&(Object.hasOwn(t.people_transfer,'face_style')||Object.hasOwn(t.people_transfer,'face_style_visual')))throw Error('未请求的新版脸型目标审核');
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
      if(decoration&&!t.blocked&&(!t.people_transfer||!validDecorationEvidence(t.people_transfer,t.document_id,t.revision??'',t.people_transfer.target_owner.source_proof)))throw Error('目标缺少本人的装饰可见范围及完整前后图');
      if(decoration&&!t.blocked&&t.people_transfer){const own=t.people_transfer.face_decoration_visual!;for(const other of [t.people_transfer.eye_bag_visual,t.people_transfer.collarbone_visual])if(other&&!sameDecorationRender(own,other))throw Error('独立人物审核必须指向同一完整混合候选图像与状态');}
      if((!decoration||!!t.blocked)&&t.people_transfer&&(t.people_transfer.face_decoration_coverage!==undefined||t.people_transfer.face_decoration_visual!==undefined))throw Error('未请求或受阻目标携带装饰图像证据');
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
    if(people?.target_policy==='persistent_association'&&!validCollarboneCohort(result as BatchPlan,people))throw Error('持久关联锁骨审核必须包含源成员与全部目标的真实图像及独立范围；不能用继承元数据代替。');
    if(people?.target_policy==='persistent_association'&&!validPortraitCohort(result as BatchPlan,people))throw Error('完整脸型共同参数必须包含源成员与全部目标的真实前后审核，不接受省略成员或推断命名配方。');
    if(people?.target_policy==='persistent_association'&&!validEyeBagCohort(result as BatchPlan,people))throw Error('祛眼袋关联需要源成员及所有目标各自的修改前后保护、明确旧版策略和完整真实图像。');
    if((result.face_decoration_cohort===true||result.portrait_cohort===true||result.eye_bag_cohort===true)&&(result.association_source?.document_id!==result.source_snapshot.document_id
      ||result.association_source?.revision!==result.source_snapshot.revision||result.association_source?.path!==result.source_snapshot.path))throw Error('完整脸型关联源成员与冻结源照片不一致。');
    if(result.portrait_cohort_ack!==undefined)throw Error('预检不能携带提交确认。');
    if(blocked!==result.blocked)throw Error('预检受阻数量不一致');
    return result as BatchPlan;
  }
  function checkCommitted(result:BatchReply){
    const plan=state.plan;
    if(!plan||!Array.isArray(result.target_outcomes)||result.target_outcomes.length!==plan.targets.length
      ||result.source_snapshot?.document_id!==plan.source_snapshot.document_id
      ||result.source_snapshot?.revision!==plan.source_snapshot.revision||result.source_snapshot?.path!==plan.source_snapshot.path)throw Error('提交结果缺少冻结源图或目标明细');
    checkEyeBagCohortCommit(result,plan);
    if(plan.face_decoration_cohort){const rows=[plan.association_source,...plan.targets],outcomes=[result.source_outcome,...result.target_outcomes];const marker=result.face_decoration_cohort_review;const epoch=(plan.applies as unknown as AssociationRequest).source.document.epoch;if(typeof result.batch_id!=='string'||!validDecorationBatchMarker(marker)||marker.member_count!==rows.length||outcomes.length!==rows.length||!rows.every((r,i)=>r&&outcomes[i]?.document_id===r.document_id&&outcomes[i]?.outcome==='applied'&&outcomes[i]?.path===r.path&&outcomes[i]?.expected_revision===r.revision)||!registerDecorationMultiHistory(epoch,result.batch_id,'face_decoration_cohort_review',marker))throw Error('装饰关联必须证明源成员与全部目标原子发布及精确历史');}
    const decoration=plan.face_decoration_visual_required===true;
    if(decoration&&result.batch_id!==null&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||result.batch_id.length>128))throw Error('装饰批次身份无效');
    const eyeBag=plan.applies.target_policy==='explicit_face_map'&&Object.hasOwn(plan.applies,'eye_bag');
    if(eyeBag&&result.batch_id!==null&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||result.batch_id.length>128||/[\u0000-\u001f\u007f]/.test(result.batch_id)))throw Error('祛眼袋提交缺少可追溯批次或明确无改动结果。');
    const head=plan.module_scope.includes(HEAD_OP);
    const faceStyle=plan.applies.target_policy==='explicit_face_map'&&validFaceStyleRecipe(plan.applies.face_style);
    if(faceStyle&&result.batch_id!==null&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||result.batch_id.length>128
      ||/[\u0000-\u001f\u007f]/.test(result.batch_id)))throw Error('新版脸型提交缺少可追溯的批次身份');
    if(plan.portrait_cohort&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||result.batch_id.length>128||/[\u0000-\u001f\u007f]/.test(result.batch_id)))throw Error('持久人物关联提交缺少真实批次身份；相同意图应在写入前拒绝。');
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
        ||!((eyeBag||decoration)?['applied','skipped','noop']:['applied','skipped']).includes(target.outcome??''))throw Error('提交结果与预检目标不一致');
      if((eyeBag||decoration)&&['applied','noop'].includes(target.outcome??'')&&(!!before.blocked||!!target.blocked
        ||target.current_revision!==before.revision||!revision(target.result_revision)
        ||(target.outcome==='noop'?target.result_revision!==before.revision:BigInt(target.result_revision)<=BigInt(before.revision??'0'))
        ||target.outcome==='applied'&&result.batch_id===null))throw Error('祛眼袋目标的无改动或实际写入版本与冻结审核不同。');
      if(faceStyle&&(target.outcome==='applied'&&(!!before.blocked||!!target.blocked||!revision(target.result_revision)
        ||BigInt(target.result_revision)<BigInt(before.revision??'0')
        ||result.batch_id===null&&target.result_revision!==before.revision)))throw Error('新版脸型提交版本与冻结目标或无改动结果不一致');
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
    if(decoration&&(result.target_outcomes.some(target=>target.outcome==='applied')?result.batch_id===null:result.batch_id!==null))throw Error('装饰批次与实际发生的改动不一致');
    if(decoration&&result.batch_id===null&&result.face_decoration_batch_review!==undefined)throw Error('无改动结果不得携带装饰批次标记');
    if(decoration&&result.batch_id){
      const members=result.target_outcomes.filter(target=>target.outcome==='applied').length;
      const source=(plan.applies as unknown as import('../people/transferProof').ExplicitPeopleRequest).source;
      if(!validDecorationBatchMarker(result.face_decoration_batch_review)||result.face_decoration_batch_review.member_count!==members||!registerDecorationBatchReceipt(source.document.epoch,result.batch_id,members,result.face_decoration_batch_review.review_sha256))throw Error('装饰批次工作区或成员身份不匹配');
    }
    if(eyeBag&&(result.target_outcomes.some(target=>target.outcome==='applied')?result.batch_id===null:result.batch_id!==null))throw Error('祛眼袋批次身份与实际发生的改动不一致。');
    if(eyeBag&&result.batch_id){
      const members=result.target_outcomes.filter(target=>target.outcome==='applied').length;
      eyeBagBatchIds.set(result.batch_id,members);
      const source=(plan.applies as unknown as import('../people/transferProof').ExplicitPeopleRequest).source;
      registerEyeBagBatchReceipt(source.document.epoch,result.batch_id,members);
    }
    if(plan.eye_bag_cohort&&result.batch_id){
      const members=plan.targets.length+1;eyeBagBatchIds.set(result.batch_id,members);
      registerEyeBagCohortReceipt(plan.association_source!.association!.owner.document.epoch,result.batch_id,members);
    }
    if(head&&JSON.stringify(result.targets)!==JSON.stringify(result.target_outcomes.filter(target=>target.outcome==='applied').map(target=>target.index)))throw Error('小头实际应用行清单与逐图终态不一致');
    if(faceStyle&&result.batch_id)faceStyleBatchIds.add(result.batch_id);
    if(plan.portrait_cohort&&result.batch_id)portraitCohortBatchIds.add(result.batch_id);
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
          checkEyeBagCohortReceipt(result,request);
          if(result.eye_bag_recovery_alias_review!==undefined&&(!request.recoveryAliasWrite||!request.recoveryAliasMarker||!sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,request.recoveryAliasMarker)))throw Error('未请求或不匹配的共享来源效果恢复历史标记，只能查询原请求。');
          if(request.recoveryAliasWrite&&(!validBodyScalarReceiptState(result)||!['undo','redo'].includes(request.action)
            ||(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId))throw Error('共享来源恢复历史回执不属于原批次或终态不明确，只能查询原请求。');
          if(request.recoveryAliasWrite&&!result.success&&result.outcome_unknown===false
            &&(!(result.no_write===true&&result.rolled_back!==true||result.no_write===false&&result.rolled_back===true)||result.batch_id!==request.batchId||!request.recoveryAliasMarker
              ||!sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,request.recoveryAliasMarker)
              ||JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])||!Array.isArray(result.restored)||result.restored.length!==0
              ||typeof result.error!=='string'||!result.error.trim()||['doc_state','before','after','applied','committed','operation_committed'].some(field=>Object.hasOwn(result,field))))throw Error('共享来源恢复历史失败未证明未发布或完整回滚，只能查询原请求。');
          if(result.eye_bag_preset_alias_review!==undefined&&(!request.presetAliasWrite||!request.presetAliasMarker||!sameEyeBagPresetAliasMarker(result.eye_bag_preset_alias_review,request.presetAliasMarker)))throw Error('未请求或不匹配的混合预设共享来源历史标记，只能查询原请求。');
          if(request.presetAliasWrite&&(!validBodyScalarReceiptState(result)||!['undo','redo'].includes(request.action)
            ||(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId))throw Error('共享来源混合预设历史回执不属于原批次或终态不明确，只能查询原请求。');
          if(result.eye_bag_review_ack!==undefined&&(request.action!=='commit'||request.eyeBagAck===undefined))throw Error('未请求的祛眼袋逐目标确认回执。');
          if(request.eyeBagWrite&&!validBodyScalarReceiptState(result))throw Error('祛眼袋写入缺少明确且一致的终态，只能查询原请求。');
          if(request.eyeBagWrite&&['undo','redo'].includes(request.action)&&(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId)throw Error('祛眼袋撤销/重做回执不属于原批次，只能查询原请求。');
          const eyeBagNoWrite=bodyScalarNoWriteRejection(result,request.token)
            &&!['eye_bag_review_ack','eye_bag_visual','eye_bag_coverage','eye_bag'].some(field=>Object.hasOwn(result,field));
          if(request.eyeBagAck!==undefined&&!eyeBagNoWrite&&(result.preflight_token!==request.token
            ||JSON.stringify(result.module_scope)!==JSON.stringify(request.scope)
            ||!sameEyeBagBatchAck(result.eye_bag_review_ack,request.eyeBagAck)))throw Error('祛眼袋终态、完整混合范围、旧版策略或有序图像确认不匹配，只能查询原请求。');
          if([result.face_decoration_batch_review,result.face_decoration_cohort_review,result.face_decoration_alias_review].some(v=>v!==undefined)&&!request.decorationWrite)throw Error('未请求的装饰历史标记');
          if(request.decorationWrite&&!validBodyScalarReceiptState(result))throw Error('装饰写入缺少明确一致的终态，只能查询原请求');
          if(request.decorationWrite&&['undo','redo'].includes(request.action)&&(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId)throw Error('装饰历史回执不属于原批次');
          if(result.face_decoration_review_ack!==undefined&&(request.action!=='commit'||request.decorationAck===undefined))throw Error('未请求的装饰逐图确认回执');
          if(result.face_decoration_cohort_ack!==undefined&&request.decorationCohortAck===undefined)throw Error('未请求的装饰关联确认');
          const decorationCohortNoWrite=bodyScalarNoWriteRejection(result,request.token)&&!['face_decoration_cohort','face_decoration_cohort_ack','face_decoration_cohort_review','face_decoration_cohort_visual','persistent_association','association_source','source_outcome'].some(field=>Object.hasOwn(result,field));
          if(result.face_decoration_cohort!==undefined&&request.action!=='preflight'&&request.decorationCohortAck===undefined)throw Error('未请求的装饰全成员审核标记');
          if(request.decorationCohortAck!==undefined&&!decorationCohortNoWrite&&(result.preflight_token!==request.token||result.face_decoration_cohort!==true||JSON.stringify(result.module_scope)!==JSON.stringify(request.scope)||!sameDecorationCohortAck(result.face_decoration_cohort_ack,request.decorationCohortAck)))throw Error('装饰关联回执与完整成员审核不匹配');
          if(request.decorationAck!==undefined&&(!validBodyScalarReceiptState(result)||!bodyScalarNoWriteRejection(result,request.token)&&(result.preflight_token!==request.token||JSON.stringify(result.module_scope)!==JSON.stringify(request.scope)||!sameDecorationAck(result.face_decoration_review_ack,request.decorationAck))))throw Error('装饰批次终态或逐图确认不匹配，只能查询原请求');
          if(result.collarbone_cohort!==undefined&&request.action!=='preflight'&&request.collarboneCohort!==true)throw Error('未请求的锁骨全成员审核回执');
          if(result.collarbone_review_ack!==undefined&&(request.action!=='commit'||request.collarboneAck===undefined))throw Error('未请求的锁骨逐图确认回执');
          if(request.collarboneAck!==undefined&&(!validBodyScalarReceiptState(result)||!bodyScalarNoWriteRejection(result,request.token)&&(result.preflight_token!==request.token||(request.collarboneCohort?result.collarbone_cohort!==true:result.collarbone_cohort!==undefined||!result.module_scope?.includes(COLLARBONE_OP))||!sameCollarboneAck(result.collarbone_review_ack,request.collarboneAck))))throw Error('锁骨终态或逐图确认回执不匹配，只能查询原请求');
          if(result.face_style_review_ack!==undefined&&(request.action!=='commit'||request.faceStyleAck===undefined))throw Error('未请求的新版脸型逐图确认回执');
          if(request.faceStyleWrite&&!validBodyScalarReceiptState(result))throw Error('新版脸型写入缺少明确且一致的终态，只能查询原请求');
          if(request.faceStyleWrite&&['undo','redo'].includes(request.action)
            &&(result.success||result.batch_id!=null)&&result.batch_id!==request.batchId)
            throw Error('新版脸型撤销/重做回执不属于原批次，只能查询原请求');
          const faceStyleNoWrite=bodyScalarNoWriteRejection(result,request.token)
            &&!['face_style_review_ack','face_style_visual','face_style'].some(field=>Object.hasOwn(result,field));
          if(request.faceStyleAck!==undefined&&!faceStyleNoWrite&&(result.preflight_token!==request.token
            ||JSON.stringify(result.module_scope)!==JSON.stringify(Object.keys(faceStyleSelection()))
            ||!sameFaceStyleBatchAck(result.face_style_review_ack,request.faceStyleAck)))throw Error('新版脸型终态、冻结令牌、参数范围或逐图配方确认不匹配，只能查询原请求');
          if(result.portrait_cohort!==undefined&&request.action!=='preflight'&&request.portraitAck===undefined)throw Error('未请求的完整脸型关联审核回执');
          if(result.portrait_cohort_ack!==undefined&&(request.action!=='commit'||request.portraitAck===undefined))throw Error('未请求的完整脸型关联确认回执');
          if(request.portraitWrite&&!validBodyScalarReceiptState(result))throw Error('持久人物关联写入缺少明确终态，只能查询原请求');
          const portraitNoWrite=bodyScalarNoWriteRejection(result,request.token)
            &&!['portrait_cohort','portrait_cohort_ack','portrait_visual','persistent_association','association_source','source_outcome','face_style','face_style_review_ack'].some(field=>Object.hasOwn(result,field));
          if(request.portraitAck!==undefined&&!portraitNoWrite&&(result.preflight_token!==request.token||result.portrait_cohort!==true
            ||JSON.stringify(result.module_scope)!==JSON.stringify(request.scope)||!samePortraitCohortAck(result.portrait_cohort_ack,request.portraitAck)))throw Error('持久人物关联回执的冻结令牌、完整范围或源成员优先确认不匹配，只能查询原请求');
          if(result.torso_review_ack!==undefined&&(request.action!=='commit'||result.module_scope?.length!==1||result.module_scope[0]!==TORSO_OP||result.preflight_token!==request.token||!sameTorsoTransferAck(result.torso_review_ack,request.torsoAck)))throw Error('上身长度提交回执与本次逐图确认不一致');
          if(request.action==='commit'&&request.torsoAck!==undefined&&result.success&&!sameTorsoTransferAck(result.torso_review_ack,request.torsoAck))throw Error('缺少上身长度 PNG 对确认的终态回执');
          if(result.success&&request.action==='commit'&&result.preflight_token!==request.token)throw Error('批量结果不属于本次预检');
          if(result.success&&request.action==='preflight'){
            if(request.contextKey!==key||request.contextRevision!==contextRevision){pending=null;set({phase:'error',plan:null,result:null,message:'源图、目标或参数选择已经变化，旧预检不会用于提交；请重新预检。'});return;}
            try{
              const plan=planFrom(result,request.scope??[],request.policy??'',request.transfer,request.reference,request.people,request.peopleProof,request.referencePath,request.docs);
              pending=null;set({phase:'review',plan,result:null,message:''});
            }catch(error){pending=null;set({phase:'error',plan:null,result:null,message:String(error)});}
            return;
          }
          if(result.outcome_unknown&&request.action!=='preflight'){set({phase:'uncertain',result,message:result.error??'执行结果未确认'});return;}
          if(result.success&&request.action==='commit'&&request.decorationCohortAck){const digest=await decorationCohortAckDigest(request.decorationCohortAck);if(pending!==request)return;if(result.face_decoration_cohort_review?.review_sha256!==digest)throw Error('装饰关联历史摘要与本次全部图像确认不一致');}
          if(result.success&&request.action==='commit')checkCommitted(result);
          if(result.success&&['undo','redo'].includes(request.action)&&(!Array.isArray(result.restored)||!Array.isArray(result.conflicts)))throw Error('撤销结果缺少逐张明细');
          if(result.success&&(request.decorationWrite||request.faceStyleWrite||request.eyeBagWrite||request.presetAliasWrite||request.recoveryAliasWrite)&&['undo','redo'].includes(request.action)
            &&(!result.restored!.every(index=>Number.isSafeInteger(index)&&index>=0)
              ||new Set(result.restored).size!==result.restored!.length
              ||!result.conflicts!.every(item=>object(item)&&typeof item.path==='string'&&typeof item.reason==='string'&&!!item.reason.trim())))
            throw Error('已审核人物批次撤销/重做缺少有效逐张明细，只能查询原请求');
          if(result.success&&request.recoveryAliasWrite&&['undo','redo'].includes(request.action)
            &&(!request.recoveryAliasMarker||request.recoveryAliasMemberCount==null||!sameRecoveryAliasMarker(result.eye_bag_recovery_alias_review,request.recoveryAliasMarker)
              ||JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])||result.restored!.length!==request.recoveryAliasMemberCount||result.conflicts!.length!==0))
            throw Error('效果恢复历史未证明全部原成员原子恢复，只能查询原请求。');
          if(result.success&&request.presetAliasWrite&&['undo','redo'].includes(request.action)
            &&(!request.presetAliasMarker||request.presetAliasMemberCount==null||!sameEyeBagPresetAliasMarker(result.eye_bag_preset_alias_review,request.presetAliasMarker)
              ||JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])||result.restored!.length!==request.presetAliasMemberCount||result.conflicts!.length!==0))
            throw Error('混合预设历史未证明当前照片配方与全部共享来源成员原子恢复，只能查询原请求。');
          if(result.success&&request.decorationWrite&&['undo','redo'].includes(request.action)&&(JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])||request.decorationMemberCount==null||!validDecorationBatchMarker(result[request.decorationHistoryField??'face_decoration_batch_review'])||result[request.decorationHistoryField??'face_decoration_batch_review']!.member_count!==request.decorationMemberCount||request.decorationReviewSha==null||result[request.decorationHistoryField??'face_decoration_batch_review']!.review_sha256!==request.decorationReviewSha||result.restored!.length!==request.decorationMemberCount||result.conflicts!.length!==0))throw Error('装饰历史未证明原批次全部成员原子恢复，只能查询原请求');
          if(result.success&&request.eyeBagWrite&&['undo','redo'].includes(request.action)
            &&(JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])
              ||request.eyeBagMemberCount==null||result.restored!.length!==request.eyeBagMemberCount||result.conflicts!.length!==0))
            throw Error('祛眼袋批次历史未证明完整原成员原子恢复，只能查询原请求。');
          if(result.success&&request.aliasMemberCount!==undefined&&['undo','redo'].includes(request.action)
            &&(JSON.stringify(result.module_scope)!==JSON.stringify(['lnx.people_graph.v1'])
              ||result.restored!.length!==request.aliasMemberCount||result.conflicts!.length!==0))
            throw Error('共享来源批次历史未证明完整原成员原子恢复，只能查询原请求');
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
    if(recoveryAliasWritePending()){set({message:'共享来源效果恢复仍未获得明确终态；请先查询原恢复请求，不启动新的批次或历史修改。'});return;}
    if(eyeBagPresetAliasWritePending()){set({message:'共享来源混合预设应用仍未获得明确终态；请先查询原预设请求，不启动新的批次或历史修改。'});return;}
    const recoveryHistory=recoveryAliasHistoryClass(opts.batchId);
    if(recoveryHistory&&(!recoveryHistory.marker||recoveryHistory.memberCount===null)){set({phase:'error',message:'共享来源效果恢复批次标记不完整，禁止降级为普通历史。请重新读取准确台账。'});return;}
    const g=++generation,id=uuid(),deadline=now()+(options.timeoutMs??120000);
    const decorationMulti=decorationMultiHistory(opts.batchId);
    const decorationHistory=decorationMulti?{memberCount:decorationMulti.memberCount,reviewSha256:decorationMulti.marker?.review_sha256??null}:decorationBatchHistoryClass(opts.batchId);
    const presetAliasHistory=eyeBagPresetAliasHistoryClass(opts.batchId),aliasHistory=faceStyleAliasHistoryClass(opts.batchId),eyeHistory=eyeBagAliasHistoryClass(opts.batchId)??eyeBagCohortHistoryClass(opts.batchId)??eyeBagBatchHistoryClass(opts.batchId);
    const request={id,action,generation:g,contextKey:key,contextRevision,batchId:opts.batchId,presetAliasWrite:!!presetAliasHistory,presetAliasEpoch:presetAliasHistory?eyeBagPresetAliasWorkspace():undefined,presetAliasMarker:presetAliasHistory?.marker?structuredClone(presetAliasHistory.marker):presetAliasHistory?.marker,presetAliasMemberCount:presetAliasHistory?.memberCount,aliasMemberCount:aliasHistory?.memberCount,token:opts.preflightToken,scope:opts.moduleScope?[...opts.moduleScope]:action==='commit'&&(opts.faceDecorationCohortAck!==undefined||opts.faceDecorationReviewAck!==undefined||opts.eyeBagReviewAck!==undefined||opts.eyeBagCohortAck!==undefined)?[...state.plan!.module_scope]:undefined,policy:opts.conflictPolicy,transfer:opts.localMaskTransfer,reference:opts.referenceColor,people:opts.peopleTransfer?structuredClone(opts.peopleTransfer):undefined,peopleProof:context.peopleProof?structuredClone(context.peopleProof):undefined,referencePath:context.referencePath,docs:opts.docs?[...opts.docs]:undefined,torsoAck:opts.torsoReviewAck?.map(ack=>({...ack})),waistAck:opts.waistReviewAck?.map(ack=>({...ack})),headAck:opts.headReviewAck?.map(ack=>({...ack})),decorationCohortAck:opts.faceDecorationCohortAck?.map(a=>({...a})),decorationHistoryField:decorationMulti?.field,decorationWrite:opts.faceDecorationCohortAck!==undefined||opts.faceDecorationReviewAck!==undefined||!!decorationHistory,decorationReviewSha:decorationHistory?.reviewSha256,decorationMemberCount:decorationHistory?.memberCount,decorationAck:opts.faceDecorationReviewAck?.map(ack=>({...ack})),collarboneAck:opts.collarboneReviewAck?.map(ack=>({...ack})),collarboneCohort:action==='commit'&&state.plan?.collarbone_cohort===true,
      faceStyleAck:opts.faceStyleReviewAck?.map(ack=>({...ack})),faceStyleWrite:opts.faceStyleReviewAck!==undefined||!!aliasHistory||!!opts.batchId&&faceStyleBatchIds.has(opts.batchId),
      portraitAck:opts.portraitCohortAck?.map(ack=>({...ack})),portraitWrite:opts.portraitCohortAck!==undefined||!!opts.batchId&&portraitCohortBatchIds.has(opts.batchId),
      eyeBagAck:opts.eyeBagReviewAck?.map(ack=>({...ack})),eyeBagCohortAck:opts.eyeBagCohortAck?.map(ack=>({...ack})),eyeBagWrite:opts.eyeBagReviewAck!==undefined||opts.eyeBagCohortAck!==undefined||!!eyeHistory||!!opts.batchId&&eyeBagBatchIds.has(opts.batchId),
      eyeBagMemberCount:eyeHistory?eyeHistory.memberCount:opts.batchId?eyeBagBatchIds.get(opts.batchId):undefined,
      recoveryAliasWrite:!!recoveryHistory,recoveryAliasEpoch:recoveryHistory?recoveryAliasWorkspace():undefined,recoveryAliasMarker:recoveryHistory?.marker?structuredClone(recoveryHistory.marker):recoveryHistory?.marker,recoveryAliasMemberCount:recoveryHistory?.memberCount};pending=request;
    set({phase:action==='preflight'?'preflighting':'committing',hidden:false,queryOnly:request.decorationWrite||request.faceStyleWrite||request.portraitWrite||request.eyeBagWrite||request.presetAliasWrite||request.recoveryAliasWrite,operation:action,result:null,message:''});
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
    if(context.peopleTransfer?.target_policy==='persistent_association'&&Object.hasOwn(context.peopleTransfer,'eye_bag_cohort')
      &&(!samePeopleRequest(context.peopleTransfer,context.peopleTransfer)||context.docs.length>15||context.conflictPolicy!=='recheck'
        ||context.referenceColor!==undefined||context.localMaskTransfer!==undefined)){
      set({phase:'error',plan:null,result:null,message:'祛眼袋关联需要包含源图的准确全成员策略，不传递保护、分析或恢复数据。'});return;
    }
    if(context.peopleTransfer?.target_policy==='explicit_face_map'&&context.peopleTransfer.eye_bag!==undefined
      &&(!samePeopleRequest(context.peopleTransfer,context.peopleTransfer)||context.docs.length>EYE_BAG_BATCH_LIMIT
        ||!context.moduleScope.includes(EYE_BAG_BATCH_OP)||context.referenceColor!==undefined||context.localMaskTransfer!==undefined)){
      set({phase:'error',plan:null,result:null,message:'祛眼袋同步需要准确的手动人脸配对与每张目标明确的旧版处理策略；不传递保护或恢复数据。'});return;
    }
    if(context.peopleTransfer?.target_policy==='explicit_face_map'&&context.peopleTransfer.face_style!==undefined
      &&(!samePeopleRequest(context.peopleTransfer,context.peopleTransfer)||context.docs.length>FACE_STYLE_BATCH_LIMIT
        ||JSON.stringify(context.moduleScope)!==JSON.stringify(Object.keys(faceStyleSelection()))||context.referenceColor!==undefined||context.localMaskTransfer!==undefined)){
      set({phase:'error',plan:null,result:null,message:'新版脸型仅支持逐张明确指定目标和完整的 30 项配方，不接受其他参数或自动关联。'});return;
    }
    if(context.peopleTransfer?.target_policy==='persistent_association'&&context.peopleTransfer.face_style!==undefined
      &&(!samePeopleRequest(context.peopleTransfer,context.peopleTransfer)||context.docs.length>15||context.conflictPolicy!=='recheck'
        ||JSON.stringify(context.moduleScope)!==JSON.stringify(Object.keys(faceStyleSelection()))||context.referenceColor!==undefined||context.localMaskTransfer!==undefined)){
      set({phase:'error',plan:null,result:null,message:'命名脸型持久关联必须逐张选择唯一成员、完整 30 项配方和统一程度，不能混用其他操作。'});return;
    }
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
  async function commit(spillReviewAck?:SpillTransferAck[],shadowReviewAck?:ShadowTransferAck[],torsoReviewAck?:TorsoTransferAck[],waistReviewAck?:WaistTransferAck[],headReviewAck?:HeadTransferAck[],collarboneReviewAck?:CollarboneAck[],faceStyleReviewAck?:FaceStyleBatchAck[],portraitCohortReviewAck?:PortraitCohortAck[],eyeBagReviewAck?:EyeBagBatchAck[],eyeBagCohortReviewAck?:EyeBagCohortAck[],faceDecorationReviewAck?:DecorationAck[],faceDecorationCohortAck?:DecorationAck[]){
    if(state.phase!=='review'||!state.plan||state.plan.ok<1)return;
    const eyeBagCohortAckSnapshot=eyeBagCohortReviewAck?.map(ack=>({...ack}));
    const faceStyleAckSnapshot=faceStyleReviewAck?.map(ack=>({...ack})),portraitAckSnapshot=portraitCohortReviewAck?.map(ack=>({...ack})),eyeBagAckSnapshot=eyeBagReviewAck?.map(ack=>({...ack})),collarboneAckSnapshot=collarboneReviewAck?.map(ack=>({...ack}));
    if(state.plan.policy==='recheck'&&state.plan.blocked>0){set({message:'有受阻目标，请重新预检或修改选择'});return;}
    const collarbone=state.plan.collarbone_cohort===true||state.plan.module_scope.includes(COLLARBONE_OP);
    const collarboneTargets=collarbonePlanTargets(state.plan);
    const spill=state.plan.module_scope.includes(SPILL_OP),targets=state.plan.targets.filter(target=>!target.blocked);
    const decorationCohort=state.plan.face_decoration_cohort===true,cohortAck=faceDecorationCohortAck?.map(a=>({...a}));
    if(decorationCohort){const frozen=state.plan,contextKey=key,version=contextRevision,targets=decorationCohortTargets(frozen);if(targets.length!==frozen.targets.length+1||!sameDecorationCohortAck(cohortAck,decorationCohortAck(targets))){set({message:'请查看并确认源成员与全部目标的完整装饰前后效果'});return;}const verified=await Promise.all(targets.map(t=>verifyDecorationCoverage(t.visual,t.coverage)));if(disposed||state.phase!=='review'||key!==contextKey||contextRevision!==version||state.plan!==frozen||verified.some(v=>!v)){set({message:'装饰关联审核已变化，请重新预检'});return;}}else if(faceDecorationCohortAck!==undefined){set({message:'装饰关联确认不属于当前预检'});return;}
    const decoration=state.plan.face_decoration_visual_required===true,decorationSnapshot=faceDecorationReviewAck?.map(ack=>({...ack}));
    if(decoration){
      const plan=state.plan,reviewKey=key,reviewRevision=contextRevision;
      if(targets.length>16||!targets.length||targets.some(t=>!t.people_transfer||!validDecorationEvidence(t.people_transfer,t.document_id,t.revision??'',t.people_transfer.target_owner.source_proof))||!sameDecorationAck(decorationSnapshot,decorationAck(targets.map(t=>t.people_transfer!.face_decoration_visual!)))){set({message:'请逐张读取并确认各目标完整编辑链及其已有装饰的真实前后效果。'});return;}
      const checked=await Promise.all(targets.map(t=>verifyDecorationCoverage(t.people_transfer!.face_decoration_visual!,t.people_transfer!.face_decoration_coverage!)));
      if(checked.some(ok=>!ok)||state.plan!==plan||state.phase!=='review'||key!==reviewKey||contextRevision!==reviewRevision||disposed){set({message:'装饰目标或审核内容已改变，请重新预检。'});return;}
    }else if(faceDecorationReviewAck!==undefined){set({message:'装饰确认不属于当前冻结批次。'});return;}
    const namedRecipe=state.plan.applies.face_style,faceStyle=state.plan.applies.target_policy==='explicit_face_map'&&validFaceStyleRecipe(namedRecipe);
    const portrait=state.plan.portrait_cohort===true,portraitTargets=portraitCohortTargets(state.plan);
    const eyeBag=state.plan.applies.target_policy==='explicit_face_map'&&Object.hasOwn(state.plan.applies,'eye_bag');
    const eyeCohort=state.plan.eye_bag_cohort===true;
    if(eyeCohort){
      const plan=state.plan,reviewContext=key,reviewRevision=contextRevision,cohortTargets=eyeBagCohortTargets(plan);
      if(plan.applies.target_policy!=='persistent_association'||!validEyeBagCohort(plan,plan.applies as unknown as import('../people/associationProof').AssociationRequest)
        ||cohortTargets.length!==targets.length+1||[spillReviewAck,shadowReviewAck,torsoReviewAck,waistReviewAck,headReviewAck,faceStyleReviewAck,eyeBagReviewAck].some(ack=>ack!==undefined)
        ||!validEyeBagCohortAck(eyeBagCohortAckSnapshot,cohortTargets)){set({message:'请逐张读取并确认源成员和全部目标的前后效果、双方本地卧蚕保护与各自旧版策略。'});return;}
      const verified=await Promise.all(cohortTargets.map(row=>verifyEyeBagCohortCoverage(row.visual,row.coverage)));
      if(disposed||state.phase!=='review'||state.plan!==plan||key!==reviewContext||contextRevision!==reviewRevision)return;
      if(!verified.every(Boolean)){set({message:'成员修改前后保护摘要不匹配，请重新预检；未发送修改。'});return;}
    }else if(eyeBagCohortReviewAck!==undefined){set({message:'祛眼袋全成员确认不属于当前冻结关联。'});return;}
    if(eyeBag){
      const plan=state.plan,reviewContext=key;
      const people=plan.applies as unknown as import('../people/transferProof').ExplicitPeopleRequest;
      if(!samePeopleRequest(people,people)||!people.eye_bag||faceStyle||portrait
        ||targets.some(target=>{const policy=people.eye_bag!.targets.find(row=>row.document_id===target.document_id);return !policy||!target.people_transfer||!validEyeBagBatchReview(target.people_transfer,policy.replace_legacy);})
        ||!validEyeBagBatchAck(eyeBagAckSnapshot,targets.map(target=>target.people_transfer!))){set({message:'请逐张读取并确认目标自己的卧蚕保护、旧版处理策略与全部所选参数的真实前后图。'});return;}
      const verified=await Promise.all(targets.map(target=>verifyEyeBagBatchCoverage(target.people_transfer!.eye_bag_visual!,target.people_transfer!.eye_bag_coverage!)));
      if(disposed||state.phase!=='review'||state.plan!==plan||key!==reviewContext)return;
      if(!verified.every(Boolean)){set({message:'祛眼袋覆盖摘要不匹配，请重新预检；未发送修改。'});return;}
    }else if(eyeBagReviewAck!==undefined){set({message:'祛眼袋确认不属于当前冻结策略。'});return;}
    if(portrait){
      if(state.plan.applies.target_policy!=='persistent_association'||!validPortraitCohort(state.plan,state.plan.applies as unknown as import('../people/associationProof').AssociationRequest)
        ||portraitTargets.length!==targets.length+1||[spillReviewAck,shadowReviewAck,torsoReviewAck,waistReviewAck,headReviewAck,faceStyleReviewAck].some(ack=>ack!==undefined)
        ||!validPortraitCohortAck(portraitAckSnapshot,portraitTargets.map(row=>row.visual))){set({message:'请读取并逐张确认源成员及全部目标的真实前后图，不能只确认目标或借用旧的成员审核。'});return;}
    }else if(portraitCohortReviewAck!==undefined){set({message:'完整脸型关联确认不属于当前冻结范围。'});return;}
    if(faceStyle){
      const plan=state.plan,reviewContext=key;
      if(plan.applies.target_policy!=='explicit_face_map'||!samePeopleRequest(plan.applies,plan.applies as unknown as PeopleTransferRequest)
        ||JSON.stringify(plan.module_scope)!==JSON.stringify(Object.keys(faceStyleSelection()))
        ||[spillReviewAck,shadowReviewAck,torsoReviewAck,waistReviewAck,headReviewAck,collarboneReviewAck].some(ack=>ack!==undefined)
        ||targets.some(target=>!target.people_transfer||!sameFaceStyleRecipe(target.people_transfer.face_style,namedRecipe)
          ||!validFaceStyleBatchVisual(target.people_transfer.face_style_visual,target.people_transfer))
        ||!validFaceStyleBatchAck(faceStyleAckSnapshot,targets.map(target=>target.people_transfer!.face_style_visual!))){
        set({message:'请逐张查看并确认所有目标的新版脸型真实前后效果，配方名称、程度与 30 项范围必须一致。'});return;
      }
      const verified=await Promise.all(targets.map(target=>verifyFaceStyleBatchRecipe(target.people_transfer!.face_style_visual!,namedRecipe)));
      // Digest work must never resume a closed, changed, replaced or already-submitted review.
      if(disposed||state.phase!=='review'||state.plan!==plan||key!==reviewContext)return;
      if(!verified.every(Boolean)){set({message:'新版脸型配方摘要不匹配，请重新预检；未发送修改。'});return;}
    }else if(faceStyleReviewAck!==undefined||Object.hasOwn(state.plan.applies,'face_style')&&!portrait){
      set({message:'新版脸型确认不属于当前有效的冻结配方。'});return;
    }
    if(collarbone&&(collarboneTargets.length!==targets.length+(state.plan.collarbone_cohort?1:0)||(state.plan.collarbone_cohort===true?state.plan.applies.target_policy!=='persistent_association'||!validCollarboneCohort(state.plan,state.plan.applies as unknown as import('../people/associationProof').AssociationRequest):targets.some(t=>!t.people_transfer||!validCollarboneVisual(t.people_transfer.collarbone_visual,t.people_transfer)))||!validCollarboneAck(collarboneAckSnapshot,collarboneTargets.map(t=>t.visual)))){set({message:'请逐图查看并确认所有目标的真实锁骨前后效果，包括归零。'});return;}
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
    await submit('commit',{preflightToken:state.plan.preflight_token,...(decorationCohort?{faceDecorationCohortAck:cohortAck!,moduleScope:[...state.plan.module_scope]}:{}),...(decoration?{faceDecorationReviewAck:decorationSnapshot!}:{}),...(spill?{spillReviewAck:spillReviewAck!.map(ack=>({...ack}))}:{}),...(shadow?{shadowReviewAck:shadowReviewAck!.map(ack=>({...ack}))}:{}),...(torso?{torsoReviewAck:torsoReviewAck!.map(ack=>({...ack}))}:{}),...(waist?{waistReviewAck:waistReviewAck!.map(ack=>({...ack}))}:{}),...(head?{headReviewAck:headReviewAck!.map(ack=>({...ack}))}:{}),...(collarbone?{collarboneReviewAck:collarboneAckSnapshot!}:{}),...(eyeBag?{eyeBagReviewAck:eyeBagAckSnapshot!}:{}),...(eyeCohort?{eyeBagCohortAck:eyeBagCohortAckSnapshot!,moduleScope:[...state.plan.module_scope]}:{}),...(faceStyle?{faceStyleReviewAck:faceStyleAckSnapshot!}:{}),...(portrait?{portraitCohortAck:portraitAckSnapshot!,moduleScope:[...state.plan.module_scope]}:{})});
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
    if(pending?.recoveryAliasWrite){set({message:'共享来源效果恢复历史结果尚未确定，只能查询原请求，不能结束跟踪后重复撤销或重做。'});return;}
    if(pending?.presetAliasWrite){set({message:'共享来源混合预设历史结果尚未确定，只能查询原请求，不能结束跟踪后重复撤销或重做。'});return;}
    if(pending?.eyeBagWrite){set({message:'祛眼袋写入结果尚未确定，只能查询原请求，不能结束跟踪后重复提交。'});return;}
    if(pending?.portraitWrite){set({message:'持久人物关联写入结果尚未确定，只能查询原请求，不能结束跟踪后重复提交。'});return;}
    if(pending?.faceStyleWrite){set({message:'新版脸型写入结果尚未确定，只能查询原请求；不能结束跟踪后重复提交。'});return;}
    if(pending?.waistAck!==undefined){set({message:'腰长提交结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    if(pending?.headAck!==undefined){set({message:'小头提交结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    if(pending?.decorationWrite){set({message:'装饰批次写入结果尚未确定，只能查询原请求，不能释放后重复提交。'});return;}
    if(pending?.collarboneAck!==undefined){set({message:'锁骨同步结果尚未确定，只能查询原请求，不能释放后重复提交。'});return;}
    generation++;pending=null;set({phase:'closed',hidden:false,queryOnly:false,result:null,plan:null,message:''});
  }
  function protectFaceStyleAlias(commit:FaceStyleAliasCommit){
    return !disposed&&registerFaceStyleAliasReceipt(commit);
  }
  function protectEyeBagAlias(commit:EyeBagAliasCommit){
    return !disposed&&registerEyeBagAliasReceipt(commit);
  }
  return {updateContext,start,commit,undo,redo,query,close,acknowledgeInspection,protectFaceStyleAlias,protectEyeBagAlias,snapshot:()=>state,dispose:()=>{stopWorkspaceRecovery();stopRecoveryWorkspace();disposed=true;generation++;pending=null;}};
}
