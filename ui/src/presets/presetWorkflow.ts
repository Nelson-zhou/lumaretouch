import {checkDecorationPresetAliasReceipt} from '../faceDecoration/presetAliasReceipt';
import {decorationPresetAliasMarker,validDecorationPresetAliasMarker,sameDecorationPresetAliasMarker,registerDecorationPresetAliasReceipt,setDecorationPresetAliasWritePending,decorationPresetAliasWritePending,subscribeDecorationPresetAliasWorkspace,type DecorationPresetAliasMarker} from '../faceDecoration/presetAliasHistoryRegistry';
import {OP as DECORATION_OP,validDecorationPreset,decorationPresetAck,sameDecorationPresetAck,verifyDecorationPreset,type DecorationPreset,type DecorationPresetAck} from '../faceDecoration/transferModel';
import {canonical as canonicalEyeBagValue} from '../eyeBagPreserve/support';
import {presetAliasMarker,sameEyeBagPresetAliasMarker,registerEyeBagPresetAliasReceipt,setEyeBagPresetAliasWritePending,subscribeEyeBagPresetAliasWorkspace,type EyeBagPresetAliasMarker} from '../eyeBagPreserve/presetAliasHistoryRegistry';
import {EYE_BAG_PRESET_OP,validEyeBagPreset,eyeBagPresetAck,sameEyeBagPresetAck,neutralEyeBagPreset,verifyEyeBagCoverage,type EyeBagPresetReview,type EyeBagPresetAck} from '../eyeBagPreserve/presetModel';
import {COLLARBONE_PRESET_OP,validCollarbonePreset,collarbonePresetAck,sameCollarbonePresetAck,type CollarbonePresetReview,type CollarbonePresetAck} from '../collarbone/presetModel';
import {CROP_OP,validCropReview,type CropReview} from '../cropTransfer/model.ts';
import {SPILL_TRANSFER_OP,validSpillTransfer,validSpillTransferAck,type SpillTransferEvidence,type SpillTransferAck} from '../spillRemoval/transferModel.ts';
import {SHADOW_TRANSFER_OP,validShadowTransfer,validShadowTransferAck,type ShadowTransferEvidence,type ShadowTransferAck} from '../originalShadow/transferModel.ts';
import {TORSO_TRANSFER_OP,validTorsoTransfer,validTorsoTransferAck,sameTorsoTransferAck,type TorsoTransferEvidence,type TorsoTransferAck} from '../torsoLength/transferModel.ts';
import {WAIST_TRANSFER_OP,waistTransferParameters,validWaistTransfer,validWaistTransferAck,sameWaistTransferAck,type WaistTransferEvidence,type WaistTransferAck} from '../waistLength/transferModel.ts';
import {HEAD_TRANSFER_OP,headTransferParameters,validHeadTransfer,validHeadTransferAck,sameHeadTransferAck,type HeadTransferEvidence,type HeadTransferAck} from '../headSize/transferModel.ts';
import {bodyScalarNoWriteRejection,validBodyScalarReceiptState} from '../bodyScalar/transferModel.ts';
import {validReferenceReview,type ReferenceReview} from '../referenceColor/ReferenceColorReview';
import {OPTICS_AUTO_OP,validOpticalReview,type OpticalTargetReview} from '../optics/transferReviewModel';
import {validTransferEvidence,sameTransferOptions,type MaskTransferOptions,type MaskTransferEvidence,type TransferGroupChoice} from '../localMasks/transferModel.ts';
/** Completion-only receipts. Never install a historical receipt's doc_state into controls. */
import type {PresetInfo, PresetState} from '../native';
import {validXmpAck, validXmpReport, validXmpSummary, validXmpTransfer, validXmpReviewAck, type XmpAck, type XmpReport, type XmpSummary, type XmpTransfer, type XmpReviewAck} from '../xmpImport/model.ts';
export type PresetAction = 'list'|'preflight'|'apply'|'save'|'import'|'delete'|'xmp_inspect';
export type PresetOptions = {id?:string;name?:string;path?:string;kind?:string;note?:string;force?:boolean;
  moduleScope?:string[];requestId?:string;documentId?:string;localMaskTransfer?:MaskTransferOptions;preflightToken?:string;spillReviewAck?:SpillTransferAck[];shadowReviewAck?:ShadowTransferAck[];torsoReviewAck?:TorsoTransferAck[];waistReviewAck?:WaistTransferAck[];headReviewAck?:HeadTransferAck[];faceDecorationPresetAck?:DecorationPresetAck;collarbonePresetAck?:CollarbonePresetAck;eyeBagPresetAck?:EyeBagPresetAck;eyeBagReplaceLegacy?:boolean;eyeBagNeutral?:boolean;
  xmpAck?:XmpAck;xmpReviewAck?:XmpReviewAck;/** UI-only captured expected source, never sent as authority. */xmpExpected?:XmpSummary};
export type PresetReply = {face_decoration_visual_required?:boolean;face_decoration_preset?:DecorationPreset;face_decoration_preset_ack?:DecorationPresetAck;face_decoration_preset_alias_review?:DecorationPresetAliasMarker;batch_id?:string|null;eye_bag_preset_alias_review?:EyeBagPresetAliasMarker;alias_members?:{document_id:string;expected_revision:string;result_revision:string}[];eye_bag_preset?:EyeBagPresetReview;eye_bag_preset_ack?:EyeBagPresetAck;eye_bag_replace_legacy?:boolean;collarbone_preset?:CollarbonePresetReview;collarbone_preset_ack?:CollarbonePresetAck;protocol:number;request_id:string;action:PresetAction;success:boolean;outcome_unknown:boolean;
  xmp_report?:XmpReport;xmp_transfer?:XmpTransfer;source_proof?:unknown;spill_transfer?:SpillTransferEvidence;shadow_transfer?:ShadowTransferEvidence;torso_transfer?:TorsoTransferEvidence;torso_review_ack?:TorsoTransferAck[];waist_transfer?:WaistTransferEvidence;waist_review_ack?:WaistTransferAck[];head_transfer?:HeadTransferEvidence;head_review_ack?:HeadTransferAck[];
  crop_transfer?:CropReview;reference_color?:ReferenceReview;revision?:string;optical_transfer?:OpticalTargetReview;preflight_token?:string;applies?:Record<string,unknown>;local_mask_transfer?:MaskTransferEvidence;document_id?:string|null;name?:string;id?:string;path?:string;module_scope?:string[];preset?:PresetInfo;catalog?:PresetState;
  before?:Record<string,unknown>;after?:Record<string,unknown>;doc_state?:Record<string,unknown>;
  error?:string;requires_reload?:boolean;rolled_back?:boolean;operation_committed?:boolean|null};
export type PresetContext = {enabled:boolean;editable:boolean;documentId:string;reviewContextKey?:string;sourceGroups?:TransferGroupChoice[]};
export type PresetUi = {phase:'idle'|'working'|'uncertain'|'done'|'error';action:PresetAction|null;
  result:PresetReply|null;message:string;submitted:{action:PresetAction;options:PresetOptions;requestId:string;reviewContextKey?:string;decorationAliasEpoch?:string}|null};
export type PresetTransport = {request:(action:PresetAction,options:PresetOptions)=>Promise<{requested:boolean}>;
  read:(id:string)=>Promise<{phase:string;request_id:string;result?:PresetReply;error?:string}>};
export const initialPresetUi:PresetUi = {phase:'idle',action:null,result:null,message:'',submitted:null};
const object = (value:unknown):value is Record<string,unknown> => !!value && typeof value==='object' && !Array.isArray(value);
const text = (value:unknown):value is string => typeof value==='string' && value.trim().length>0;
const batchToken=(value:unknown):value is string=>typeof value==='string'&&!!value.trim()&&!/[\u0000-\u001f\u007f]/.test(value)&&new TextEncoder().encode(value).length<=128;
const scope = (value:unknown):value is string[] => Array.isArray(value) && value.length>0 && value.every(text) && new Set(value).size===value.length;
const sameScope = (a:string[],b:string[]) => a.length===b.length && a.every(op=>b.includes(op));
const moduleKeys = (value:unknown,ops:string[]) => object(value) && sameScope(Object.keys(value),ops) && Object.values(value).every(object);
export function validatePresetReply(result:PresetReply,action:PresetAction,opts:PresetOptions,requestId:string,expectedScope?:string[]){
  if(!result || result.protocol!==1 || result.request_id!==requestId || result.action!==action
    || typeof result.success!=='boolean' || typeof result.outcome_unknown!=='boolean' || (result.success&&result.outcome_unknown))throw Error('预设回执身份或状态不完整');
  if(['apply','preflight','save'].includes(action)&&result.document_id!==opts.documentId)throw Error('预设结果不属于本次照片');
  if((opts.headReviewAck!==undefined||expectedScope?.includes(HEAD_TRANSFER_OP)||result.module_scope?.includes(HEAD_TRANSFER_OP))
    &&!validBodyScalarReceiptState(result))throw Error('小头回执含有未决或矛盾状态，只能查询原请求');
  // An explicit, pre-claim no-write rejection may omit acceptance fields. Unknown
  // and claimed receipts must retain the original token and ordered acknowledgment.
  if(result.waist_review_ack!==undefined&&(action!=='apply'||opts.waistReviewAck===undefined))throw Error('未请求的腰长逐图确认回执');
  if(action==='apply'&&opts.waistReviewAck!==undefined&&!bodyScalarNoWriteRejection(result,opts.preflightToken)
    &&(result.module_scope?.length!==1||result.module_scope[0]!==WAIST_TRANSFER_OP||result.preflight_token!==opts.preflightToken
      ||!sameWaistTransferAck(result.waist_review_ack,opts.waistReviewAck)))throw Error('腰长应用回执与原请求、冻结令牌或有序 PNG 对确认不一致');
  if(result.waist_transfer!=null&&(action!=='preflight'||!result.success||result.module_scope?.length!==1||result.module_scope[0]!==WAIST_TRANSFER_OP))throw Error('未请求或非预检的腰长像素证据');
  if(result.module_scope?.includes(WAIST_TRANSFER_OP)&&[result.head_transfer,result.torso_transfer,result.spill_transfer,result.shadow_transfer,result.crop_transfer,result.local_mask_transfer,result.reference_color,result.optical_transfer,result.xmp_transfer,result.xmp_report].some(value=>value!=null))throw Error('腰长回执不能混入其他作用域的证据');
  if(result.head_review_ack!==undefined&&(action!=='apply'||opts.headReviewAck===undefined))throw Error('未请求的小头逐图确认回执');
  if(action==='apply'&&opts.headReviewAck!==undefined&&!bodyScalarNoWriteRejection(result,opts.preflightToken)
    &&(result.module_scope?.length!==1||result.module_scope[0]!==HEAD_TRANSFER_OP||result.preflight_token!==opts.preflightToken
      ||!sameHeadTransferAck(result.head_review_ack,opts.headReviewAck)))throw Error('小头应用回执与原请求、冻结令牌或有序 PNG 对确认不一致');
  if(result.head_transfer!=null&&(action!=='preflight'||!result.success||result.module_scope?.length!==1||result.module_scope[0]!==HEAD_TRANSFER_OP))throw Error('未请求或非预检的小头像素证据');
  if(result.module_scope?.includes(HEAD_TRANSFER_OP)&&[result.waist_transfer,result.torso_transfer,result.spill_transfer,result.shadow_transfer,result.crop_transfer,result.local_mask_transfer,result.reference_color,result.optical_transfer,result.xmp_transfer,result.xmp_report].some(value=>value!=null))throw Error('小头回执不能混入其他作用域的证据');
  if(result.torso_review_ack!==undefined&&(action!=='apply'||result.module_scope?.length!==1||result.module_scope[0]!==TORSO_TRANSFER_OP||result.preflight_token!==opts.preflightToken||!sameTorsoTransferAck(result.torso_review_ack,opts.torsoReviewAck)))throw Error('上身长度应用回执与本次逐图确认不一致');
  if(action==='apply'&&opts.torsoReviewAck!==undefined&&result.success&&!sameTorsoTransferAck(result.torso_review_ack,opts.torsoReviewAck))throw Error('缺少本次上身长度 PNG 对确认的终态回执');
  if(result.torso_transfer!=null&&(action!=='preflight'||!result.success||result.module_scope?.length!==1||result.module_scope[0]!==TORSO_TRANSFER_OP))throw Error('未请求或非预检的上身长度像素证据');
  if(result.face_decoration_visual_required!==undefined&&result.face_decoration_visual_required!==true)throw Error('装饰视觉审核标记无效');
  if(result.face_decoration_preset!==undefined&&(action!=='preflight'||!result.success||result.face_decoration_visual_required!==true))throw Error('未请求的装饰完整预设证据');
  if(result.face_decoration_preset_ack!==undefined&&(action!=='apply'||opts.faceDecorationPresetAck===undefined))throw Error('未请求的装饰预设确认回执');
  const decorationAliasReceipt=checkDecorationPresetAliasReceipt(result,action,opts,expectedScope);
  if(action==='apply'&&opts.faceDecorationPresetAck!==undefined&&decorationAliasReceipt==='none'&&(!validBodyScalarReceiptState(result)||!(result.face_decoration_preset_ack===undefined&&result.face_decoration_preset===undefined&&bodyScalarNoWriteRejection(result,opts.preflightToken))
    &&(result.id!==opts.id||result.preflight_token!==opts.preflightToken||expectedScope!==undefined&&!sameScope(result.module_scope??[],expectedScope)||!sameDecorationPresetAck(result.face_decoration_preset_ack,opts.faceDecorationPresetAck))))throw Error('装饰预设终态、冻结范围或确认不匹配，只能查询原请求');
  if(result.collarbone_preset!==undefined&&(action!=='preflight'||!result.success||!result.module_scope?.includes(COLLARBONE_PRESET_OP)))throw Error('未请求的锁骨完整预设像素证据');
  if(result.collarbone_preset_ack!==undefined&&(action!=='apply'||opts.collarbonePresetAck===undefined))throw Error('未请求的锁骨预设确认回执');
  if(action==='apply'&&opts.collarbonePresetAck!==undefined&&(!validBodyScalarReceiptState(result)||!(result.collarbone_preset_ack===undefined&&result.collarbone_preset===undefined&&bodyScalarNoWriteRejection(result,opts.preflightToken))
    &&(result.id!==opts.id||result.preflight_token!==opts.preflightToken||!result.module_scope?.includes(COLLARBONE_PRESET_OP)||expectedScope!==undefined&&!sameScope(result.module_scope,expectedScope)||!sameCollarbonePresetAck(result.collarbone_preset_ack,opts.collarbonePresetAck))))throw Error('完整预设回执与冻结令牌、目标或确认不符，只能查询原请求');
  if(result.eye_bag_replace_legacy!==undefined&&(action!=='preflight'||typeof opts.eyeBagReplaceLegacy!=='boolean'||result.eye_bag_replace_legacy!==opts.eyeBagReplaceLegacy))throw Error('未请求或不匹配的旧版去眼袋替换策略');
  if(result.eye_bag_preset!==undefined&&(action!=='preflight'||!result.success||!result.module_scope?.includes(EYE_BAG_PRESET_OP)))throw Error('未请求的去眼袋完整预设证据');
  if(result.eye_bag_preset_ack!==undefined&&(action!=='apply'||opts.eyeBagPresetAck===undefined))throw Error('未请求的去眼袋预设确认');
  const aliasAck=opts.eyeBagPresetAck&&'members'in opts.eyeBagPresetAck?opts.eyeBagPresetAck:null;
  const raw=result as unknown as Record<string,unknown>;
  if(action==='apply'&&aliasAck&&result.eye_bag_preset_ack!==undefined
    &&!([['xmp_review_ack',opts.xmpReviewAck],['spill_review_ack',opts.spillReviewAck],['shadow_review_ack',opts.shadowReviewAck]] as const)
      .every(([field,expected])=>expected===undefined?!Object.hasOwn(raw,field):Object.hasOwn(raw,field)&&canonicalEyeBagValue(raw[field])===canonicalEyeBagValue(expected)))
    throw Error('共享来源混合预设的其他逐图确认与原请求不一致，只能查询原请求');
  // Expired/unclaimed tokens may echo the exact ACK without a stored module scope.
  // This exception proves a bounded no-write rejection only; it never authorizes unknown or successful writes.
  const aliasNoWrite=action==='apply'&&!!aliasAck&&validBodyScalarReceiptState(result)&&result.success===false&&result.outcome_unknown===false
    &&typeof result.error==='string'&&!!result.error.trim()&&result.id===opts.id&&result.document_id===opts.documentId&&result.preflight_token===opts.preflightToken
    &&sameEyeBagPresetAck(result.eye_bag_preset_ack,aliasAck)
    &&(result.module_scope===undefined||expectedScope!==undefined&&JSON.stringify(result.module_scope)===JSON.stringify(expectedScope))
    &&!['batch_id','eye_bag_preset_alias_review','alias_members','eye_bag_preset','before','after','doc_state'].some(field=>Object.hasOwn(result,field))
    &&raw.operation_committed!==true&&raw.committed!==true
    &&['applied','restored'].every(field=>!Object.hasOwn(raw,field)||Array.isArray(raw[field])&&raw[field].length===0);
  // A native diagnostic-only unknown can echo the captured command and a known ledger ID without publication proof.
  // Preserve that ID as a diagnostic only: never invent scope, marker, membership or permission to restore it.
  const aliasIdentityUnknown=action==='apply'&&!!aliasAck&&validBodyScalarReceiptState(result)&&result.success===false&&result.outcome_unknown===true
    &&typeof result.error==='string'&&!!result.error.trim()&&result.id===opts.id&&result.document_id===opts.documentId&&result.preflight_token===opts.preflightToken
    &&sameEyeBagPresetAck(result.eye_bag_preset_ack,aliasAck)
    &&(result.module_scope===undefined||expectedScope!==undefined&&JSON.stringify(result.module_scope)===JSON.stringify(expectedScope))
    &&(!Object.hasOwn(result,'batch_id')||batchToken(result.batch_id))
    &&!['eye_bag_preset_alias_review','alias_members','eye_bag_preset','before','after','doc_state'].some(field=>Object.hasOwn(result,field))
    &&raw.operation_committed!==true&&raw.committed!==true
    &&['applied','restored'].every(field=>!Object.hasOwn(raw,field)||Array.isArray(raw[field])&&raw[field].length===0);
  if(action==='apply'&&opts.eyeBagPresetAck!==undefined&&(!validBodyScalarReceiptState(result)||!(aliasNoWrite||aliasIdentityUnknown||result.eye_bag_preset_ack===undefined&&result.eye_bag_preset===undefined&&bodyScalarNoWriteRejection(result,opts.preflightToken))
    &&(result.id!==opts.id||result.preflight_token!==opts.preflightToken||!result.module_scope?.includes(EYE_BAG_PRESET_OP)||expectedScope!==undefined&&!sameScope(result.module_scope,expectedScope)||!sameEyeBagPresetAck(result.eye_bag_preset_ack,opts.eyeBagPresetAck))))throw Error('去眼袋完整预设回执不匹配，只能查询原请求');
  if((Object.hasOwn(result,'eye_bag_preset_alias_review')||['batch_id','alias_members'].some(field=>Object.hasOwn(result,field))&&decorationAliasReceipt==='none')&&(action!=='apply'||!aliasAck))throw Error('未请求的混合预设共享来源批次回执');
  if(action==='apply'&&aliasAck){
    const noWrite=aliasNoWrite||bodyScalarNoWriteRejection(result,opts.preflightToken)&&result.eye_bag_preset_ack===undefined;
    if(noWrite&&['batch_id','eye_bag_preset_alias_review','alias_members'].some(field=>Object.hasOwn(result,field)))throw Error('明确未写入回执不能同时宣称共享来源批次');
    if(aliasIdentityUnknown)return;
    if(!noWrite){
      if(!result.module_scope||!aliasAck.members.length||expectedScope!==undefined&&JSON.stringify(result.module_scope)!==JSON.stringify(expectedScope))throw Error('共享来源预设缺少实际模块与全成员确认');
      const marker:EyeBagPresetAliasMarker={version:1,review_sha256:aliasAck.review_sha256,preset_sha256:aliasAck.preset_sha256,applies_sha256:aliasAck.applies_sha256,
        current_document_id:aliasAck.members[0].document_id,member_count:aliasAck.members.length,selected_modules:[...result.module_scope]};
      if(result.batch_id!==undefined&&result.batch_id!==null&&(typeof result.batch_id!=='string'||!result.batch_id.trim()||/[\u0000-\u001f\u007f]/.test(result.batch_id)||new TextEncoder().encode(result.batch_id).length>128)
        ||result.eye_bag_preset_alias_review!==undefined&&!sameEyeBagPresetAliasMarker(result.eye_bag_preset_alias_review,marker))throw Error('共享来源预设批次身份或混合作用域不匹配，只能查询原请求');
      if((result.success||result.alias_members!==undefined)&&(!result.batch_id||!sameEyeBagPresetAliasMarker(result.eye_bag_preset_alias_review,marker)||!Array.isArray(result.alias_members)||result.alias_members.length!==aliasAck.members.length
        ||!result.alias_members.every((row,index)=>{const expected=aliasAck.members[index];return object(row)&&Object.keys(row).sort().join('|')==='document_id|expected_revision|result_revision'
          &&row.document_id===expected.document_id&&row.expected_revision===expected.revision&&typeof row.result_revision==='string'&&/^(0|[1-9]\d{0,15})$/.test(row.result_revision)
          &&BigInt(row.result_revision)<=BigInt(Number.MAX_SAFE_INTEGER)&&BigInt(row.result_revision)===BigInt(expected.revision)+1n;})))throw Error('共享来源混合预设未证明全部原成员一次性提交，只能查询原请求');
      if(!result.success&&(typeof result.error!=='string'||!result.error.trim()))throw Error('未确认成功的共享来源预设缺少明确失败原因');
      if(!result.success&&!result.outcome_unknown&&(['batch_id','eye_bag_preset_alias_review','alias_members','before','after','doc_state'].some(field=>Object.hasOwn(result,field))||result.operation_committed===true))throw Error('共享来源预设拒绝回执同时含有写入证据，只能查询原请求');
      if(result.success){
        const people=result.doc_state?.people,binding=object(people)?people.binding:null;
        if(!object(binding)||binding.document_id!==aliasAck.members[0].document_id||binding.document_revision!==Number(BigInt(aliasAck.members[0].revision)+1n)
          ||result.operation_committed===false||result.rolled_back===true)throw Error('共享来源预设当前人物绑定与全成员终态不匹配，只能查询原请求');
      }
    }
  }
  if(!result.success)return;
  if(action==='xmp_inspect'){
    if(!text(result.path)||result.path!==opts.path||!validXmpReport(result.xmp_report))throw Error('XMP 检查路径或有界兼容报告不匹配');
    return;
  }
  if(action==='list'){
    if(!result.catalog || result.catalog.face_decoration_review_required!==undefined&&typeof result.catalog.face_decoration_review_required!=='boolean' || result.catalog.available!==true || !Array.isArray(result.catalog.list)
      || !Array.isArray(result.catalog.errors) || !Array.isArray(result.catalog.modules)
      || result.catalog.list.some(p=>p.xmp_import!==undefined&&!validXmpSummary(p.xmp_import,Object.keys(p.modules)))
      || result.catalog.list.some(p=>Object.hasOwn(p.modules,HEAD_TRANSFER_OP)&&(Object.keys(p.modules).length!==1||!headTransferParameters(p.modules[HEAD_TRANSFER_OP])||p.xmp_import!==undefined))
      || result.catalog.list.some(p=>Object.hasOwn(p.modules,WAIST_TRANSFER_OP)&&(Object.keys(p.modules).length!==1||!waistTransferParameters(p.modules[WAIST_TRANSFER_OP])||p.xmp_import!==undefined)))throw Error('预设目录结果不完整');
    return;
  }
  if(!text(result.id) || (opts.id!==undefined&&result.id!==opts.id))throw Error('预设结果与提交的预设不一致');
  if(action==='delete'){if(!text(result.path))throw Error('缺少实际删除路径');return;}
  if(!scope(result.module_scope))throw Error('缺少实际作用模块');
  if(result.module_scope.includes(TORSO_TRANSFER_OP)&&result.module_scope.length!==1)throw Error('上身长度必须独立预检与应用，不能混合其他模块');
  if(result.module_scope.includes(WAIST_TRANSFER_OP)&&result.module_scope.length!==1)throw Error('腰长必须独立预检与应用，不能混合其他模块');
  if(result.module_scope.includes(HEAD_TRANSFER_OP)&&result.module_scope.length!==1)throw Error('小头必须独立预检与应用，不能混合其他模块');
  const wanted=action==='save'?opts.moduleScope:expectedScope;
  if(wanted&&!sameScope(result.module_scope,wanted))throw Error('实际作用模块与选择不一致');
  if(action==='preflight'){
    if((result.module_scope.includes(DECORATION_OP)||result.face_decoration_visual_required===true)&&(!result.face_decoration_visual_required||!validDecorationPreset(result.face_decoration_preset,opts.documentId??'',result.revision,result.source_proof)))throw Error('装饰预设缺少本目标完整混合前后图与可见皮肤证明');
    if(result.face_decoration_preset?.version===2&&(!validDecorationPresetAliasMarker(decorationPresetAliasMarker(result.face_decoration_preset,result.module_scope))||expectedScope!==undefined&&JSON.stringify(result.module_scope)!==JSON.stringify(expectedScope)))throw Error('装饰混合预设完整模块顺序或范围不匹配');
    if(result.module_scope.includes(EYE_BAG_PRESET_OP)&&(opts.eyeBagReplaceLegacy!==undefined||!neutralEyeBagPreset(result.applies?.[EYE_BAG_PRESET_OP]))&&(result.eye_bag_replace_legacy!==opts.eyeBagReplaceLegacy||!validEyeBagPreset(result.eye_bag_preset,opts.documentId??'',result.revision,result.source_proof,opts.eyeBagReplaceLegacy)))throw Error('去眼袋预设缺少目标逐眼支持、完整前后图或明确旧版替换策略');
    if(result.module_scope.includes(COLLARBONE_PRESET_OP)&&!validCollarbonePreset(result.collarbone_preset,opts.documentId??'',result.revision,result.source_proof))throw Error('锁骨预设缺少当前实际来源、人物覆盖和完整混合效果的前后审核');
    if(!text(result.revision)||!text(result.preflight_token)||!/^[a-f0-9]{32}$/.test(result.preflight_token)||!moduleKeys(result.applies,result.module_scope))throw Error('冻结预设预检结果不完整');
    if(result.module_scope.includes(SPILL_TRANSFER_OP)&&(!validSpillTransfer(result.spill_transfer,opts.documentId??'',result.revision,result.applies?.[SPILL_TRANSFER_OP],result.source_proof)
      ||result.module_scope.includes('lnx.id_background.v1')))throw Error('祛反光预设缺少本目标、参数及来源匹配的真实前后预览，或混入未审核背景迁移');
    if(result.module_scope.includes(SHADOW_TRANSFER_OP)&&(!validShadowTransfer(result.shadow_transfer,opts.documentId??'',result.revision,result.applies?.[SHADOW_TRANSFER_OP],result.source_proof)
      ||(result.module_scope.includes('lnx.id_background.v1')||result.module_scope.includes(SPILL_TRANSFER_OP))))throw Error('原图阴影预设缺少本目标、参数及来源匹配的真实前后预览，或混入未审核背景迁移');
    if(result.module_scope.includes(TORSO_TRANSFER_OP)&&!validTorsoTransfer(result.torso_transfer,opts.documentId??'',result.revision,result.applies?.[TORSO_TRANSFER_OP],result.source_proof))throw Error('上身长度预设缺少本目标实际身体、本人面部、独立支持审核和真实前后预览');
    if(result.module_scope.includes(WAIST_TRANSFER_OP)&&(!validWaistTransfer(result.waist_transfer,opts.documentId??'',result.revision,result.applies?.[WAIST_TRANSFER_OP],result.source_proof)
      ||result.torso_transfer!=null||result.spill_transfer!=null||result.shadow_transfer!=null||result.xmp_transfer!=null||result.local_mask_transfer!=null))throw Error('腰长预设缺少本目标实际身体、本人面部、腰部独立支持审核或真实前后预览，或混入其他审核');
    if(result.module_scope.includes(HEAD_TRANSFER_OP)&&(!validHeadTransfer(result.head_transfer,opts.documentId??'',result.revision,result.applies?.[HEAD_TRANSFER_OP],result.source_proof)
      ||result.waist_transfer!=null||result.torso_transfer!=null||result.spill_transfer!=null||result.shadow_transfer!=null||result.xmp_transfer!=null||result.local_mask_transfer!=null))throw Error('小头预设缺少本目标实际身体、本人面部、完整头部独立支持审核或真实前后预览，或混入其他审核');
    if(result.module_scope.includes('lnx.local_grade.v1')){
      if(!validTransferEvidence(result.local_mask_transfer)||!sameTransferOptions(result.local_mask_transfer.policy,opts.localMaskTransfer))throw Error('局部预设预检证据或策略不匹配');
    }
    if(result.module_scope.includes('lnx.reference_color.v1')&&(result.applies?.['lnx.reference_color.v1'] as {strength?:number})?.strength!==0&&!validReferenceReview(result.reference_color,opts.documentId??'',result.revision))throw Error('参考统一目标证据不完整');
    if(result.module_scope.includes(OPTICS_AUTO_OP)&&!validOpticalReview(result.optical_transfer,opts.documentId??'',result.revision,result.applies?.[OPTICS_AUTO_OP]))throw Error('自动镜头/透视目标预检证据不完整');
    if(result.module_scope.includes(CROP_OP)&&!validCropReview(result.crop_transfer,opts.documentId??'',result.revision,result.applies?.[CROP_OP]))throw Error('缺少匹配的本目标真实裁剪预览');
    if(opts.xmpExpected||result.xmp_report||result.xmp_transfer){
      if(!validXmpSummary(opts.xmpExpected,result.module_scope)||!validXmpReport(result.xmp_report)
        ||result.xmp_report.source_sha256!==opts.xmpExpected.source_sha256||result.xmp_report.report_sha256!==opts.xmpExpected.report.report_sha256
        ||!validXmpTransfer(result.xmp_transfer,opts.documentId??'',result.revision,opts.xmpExpected.source_sha256))throw Error('缺少匹配本预设、当前照片和冻结版本的 XMP 前后像素证据');
    }
    if(!opts.xmpExpected&&result.face_decoration_visual_required!==true&&!result.module_scope.some(op=>['lnx.local_grade.v1',OPTICS_AUTO_OP,'lnx.reference_color.v1',CROP_OP,'lnx.spill_removal.v1',SHADOW_TRANSFER_OP,TORSO_TRANSFER_OP,WAIST_TRANSFER_OP,HEAD_TRANSFER_OP,COLLARBONE_PRESET_OP,EYE_BAG_PRESET_OP].includes(op)))throw Error('预设不含需要冻结预检的模块');
    return;
  }
  if(action==='apply'){
    if(opts.preflightToken&&result.preflight_token!==opts.preflightToken)throw Error('预设应用不属于本次冻结预检');
    if(!moduleKeys(result.before,result.module_scope)||!moduleKeys(result.after,result.module_scope)
      || !object(result.doc_state)||result.doc_state.document_id!==opts.documentId)throw Error('缺少实际应用状态');
  }else{
    const preset=result.preset;
    if(!text(result.path)||!preset||preset.schema!=='lrt.preset.v1'||preset.id!==result.id||!text(preset.name)
      ||!text(preset.kind)||!moduleKeys(preset.modules,result.module_scope))throw Error('缺少实际保存的预设内容');
    if(action==='save'&&preset.name!==opts.name)throw Error('保存名称与提交不一致');
    if(result.module_scope.includes(WAIST_TRANSFER_OP)&&(!waistTransferParameters(preset.modules[WAIST_TRANSFER_OP])||preset.xmp_import!==undefined))throw Error('腰长便携预设只能包含版本与长度标量，不能包含源图支持或其他审核');
    if(result.module_scope.includes(HEAD_TRANSFER_OP)&&(!headTransferParameters(preset.modules[HEAD_TRANSFER_OP])||preset.xmp_import!==undefined))throw Error('小头便携预设只能包含版本与缩小标量，不能包含源图支持或其他审核');
    if(preset.xmp_import!==undefined&&!validXmpSummary(preset.xmp_import,result.module_scope))throw Error('XMP 预设来源摘要不完整');
    if(opts.xmpAck&&(!validXmpSummary(preset.xmp_import,result.module_scope)||!validXmpAck(opts.xmpAck,preset.xmp_import.report)
      ||!sameScope(preset.xmp_import.selected,opts.xmpAck.selected)))throw Error('导入结果与确认的 XMP 来源或参数选择不一致');
  }
}
export function createPresetWorkflow(api:PresetTransport,publish:(state:PresetUi)=>void,
  config:{uuid?:()=>string;now?:()=>number;pause?:(ms:number)=>Promise<void>;timeoutMs?:number}={}){
  const uuid=config.uuid??(()=>crypto.randomUUID()),now=config.now??(()=>performance.now());
  const pause=config.pause??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  let context:PresetContext={enabled:false,editable:false,documentId:''},state={...initialPresetUi},disposed=false,generation=0;
  let contextGeneration=0,contextKey='';
  type Pending={contextGeneration:number;id:string;action:PresetAction;options:PresetOptions;expectedScope?:string[];generation:number;eyeBagReview?:EyeBagPresetReview;decorationReview?:DecorationPreset};
  let pending:Pending|null=null;
  const active=(g:number)=>!disposed&&generation===g;
  const set=(patch:Partial<PresetUi>)=>{state={...state,...patch};if(!disposed)publish(state);};
  const stopWorkspaceRecovery=subscribeEyeBagPresetAliasWorkspace(replacement=>{
    if(disposed||pending?.eyeBagReview?.version!==2||!replacement.retiredWrites.some(row=>row.requestId===pending!.id&&row.epoch===pending!.eyeBagReview!.owner.document.epoch))return;
    // Explicitly reopened workspace supersedes this request's editing authority, not its unknown outcome.
    generation++;pending=null;
    set({phase:'error',result:null,message:'已确认进入新的项目工作区。原混合预设请求的结果仍未知，不认定成功或未执行；请核对重新打开的全部成员后再开始新操作。旧回执不能覆盖新工作区。'});
  });
  const stopDecorationWorkspaceRecovery=subscribeDecorationPresetAliasWorkspace(replacement=>{
    if(disposed||pending?.decorationReview?.version!==2||!replacement.retiredWrites.some(row=>row.requestId===pending!.id&&row.epoch===pending!.decorationReview!.owner.document.epoch))return;
    generation++;pending=null;
    set({phase:'error',result:null,message:'已确认进入新的项目工作区。原装饰混合预设结果仍未知，不认定成功或未执行；请核对重新打开的全部成员。旧回执不能覆盖新工作区。'});
  });
  function bounded<T>(promise:Promise<T>,deadline:number):Promise<T>{
    return new Promise<T>((resolve,reject)=>{
      const timer=setTimeout(()=>reject(Error('等待超时，执行结果未确认')),Math.max(1,deadline-now()));
      promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});
    });
  }
  function uncertain(request:Pending,error:unknown){
    if(!active(request.generation))return;
    if(request.action==='list'){pending=null;set({phase:'error',message:String(error)});}
    else set({phase:'uncertain',message:String(error)});
  }
  async function poll(request:Pending,deadline=now()+(config.timeoutMs??120000)){
    try{
      while(active(request.generation)){
        const response=await bounded(api.read(request.id),deadline);
        if(!active(request.generation))return;
        if(response.request_id!==request.id)throw Error('预设查询身份不匹配');
        if(response.phase==='done'){
          const result=response.result;
          if(!result)throw Error('缺少预设完成结果');
          validatePresetReply(result,request.action,request.options,request.id,request.expectedScope);
          if(request.action==='preflight'&&request.contextGeneration!==contextGeneration){pending=null;set({phase:'error',result:null,message:'目标照片或编辑上下文已经变化，旧预检不用于应用；请重新预检。'});return;}
          if(request.eyeBagReview?.version===2&&result.batch_id&&request.expectedScope&&result.eye_bag_preset_alias_review
            &&sameEyeBagPresetAliasMarker(result.eye_bag_preset_alias_review,presetAliasMarker(request.eyeBagReview,request.expectedScope))){
            // Classify only the actual validated ledger marker. A known ID alone is not publication or history authority.
            registerEyeBagPresetAliasReceipt(request.eyeBagReview.owner.document.epoch,result.batch_id,result.eye_bag_preset_alias_review);
          }
          if(request.decorationReview?.version===2&&result.batch_id&&request.expectedScope&&result.face_decoration_preset_alias_review
            &&sameDecorationPresetAliasMarker(result.face_decoration_preset_alias_review,decorationPresetAliasMarker(request.decorationReview,request.expectedScope))){
            registerDecorationPresetAliasReceipt(request.decorationReview.owner.document.epoch,result.batch_id,result.face_decoration_preset_alias_review);
          }
          if(result.outcome_unknown){if(request.action==='list')pending=null;set({phase:request.action==='list'?'error':'uncertain',result,message:result.error??'执行结果未确认，请先核对实际状态'});return;}
          if(request.eyeBagReview?.version===2)setEyeBagPresetAliasWritePending(request.id,false);
          if(request.decorationReview?.version===2)setDecorationPresetAliasWritePending(request.id,false);
          pending=null;set({phase:result.success?'done':'error',result,message:result.error??''});return;
        }
        if(response.phase!=='pending')throw Error(response.error??'结果不可查，不代表操作未执行');
        if(now()>=deadline)throw Error('尚未确认执行结果；只能继续查询，不能自动重试');
        await pause(150);
      }
    }catch(error){uncertain(request,error);}
  }
  async function submit(action:PresetAction,options:PresetOptions={},expectedScope?:string[]){
    if(disposed||pending||state.phase==='working'||state.phase==='uncertain')return;
    const editing=['apply','preflight','save'].includes(action);
    if(editing&&decorationPresetAliasWritePending()){set({message:'装饰混合预设仍未获得明确终态；只能查询原请求，不能在其他照片或面板重新修改。'});return;}
    if(!context.enabled||(editing&&(!context.editable||!context.documentId))){
      set({phase:'error',action,result:null,message:editing?'需要可编辑照片和支持预设回执的配套引擎':'当前引擎不支持预设回执'});return;
    }
    if(action==='save'&&(!options.name?.trim()||!scope(options.moduleScope))){
      set({phase:'error',action,result:null,message:'请填写名称并明确选择保存模块'});return;
    }
    if(action==='save'&&Array.from(options.name??'').length>80){
      set({phase:'error',action,result:null,message:'预设名称最多 80 个字符，请缩短后保存'});return;
    }
    if((action==='xmp_inspect'&&!text(options.path))||(options.xmpAck&&(action!=='import'||!validXmpAck(options.xmpAck)))){
      set({phase:'error',action,result:null,message:'缺少有效的 XMP 路径或明确的参数适配确认'});return;
    }
    if(options.xmpExpected&&(!validXmpSummary(options.xmpExpected,expectedScope)
      ||(action==='apply'&&(!options.preflightToken||!validXmpReviewAck(options.xmpReviewAck)
        ||options.xmpReviewAck.source_sha256!==options.xmpExpected.source_sha256||options.xmpReviewAck.report_sha256!==options.xmpExpected.report.report_sha256)))){
      set({phase:'error',action,result:null,message:'XMP 预设必须先检查当前照片的完整前后像素并确认'});return;
    }
    const frozen=state.action==='preflight'&&state.phase==='done'&&state.result?.success?state.result:null;
    if(options.eyeBagReplaceLegacy!==undefined&&action!=='preflight'){set({message:'旧版替换选择只能随预检冻结；应用必须使用原确认。'});return;}
    if(action==='preflight'&&expectedScope?.includes(EYE_BAG_PRESET_OP)&&!options.eyeBagNeutral&&typeof options.eyeBagReplaceLegacy!=='boolean'){set({message:'请明确选择是否替换目标旧版去眼袋。'});return;}
    const eyeBag=action==='apply'&&(!options.eyeBagNeutral&&expectedScope?.includes(EYE_BAG_PRESET_OP)||frozen?.eye_bag_preset!==undefined||options.eyeBagPresetAck!==undefined);
    if(eyeBag&&(!frozen?.eye_bag_preset||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token||options.id!==frozen.id||frozen.document_id!==context.documentId
      ||state.submitted?.reviewContextKey!==context.reviewContextKey||!frozen.module_scope?.includes(EYE_BAG_PRESET_OP)||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validEyeBagPreset(frozen.eye_bag_preset,context.documentId,frozen.revision,frozen.source_proof,state.submitted?.options.eyeBagReplaceLegacy)
      ||!sameEyeBagPresetAck(options.eyeBagPresetAck,eyeBagPresetAck(frozen.eye_bag_preset)))){set({message:'请先查看目标逐眼保护和完整预设前后效果，并确认冻结的替换策略。'});return;}
    if(eyeBag&&frozen?.eye_bag_preset){
      const capturedContext=contextGeneration,verified=await verifyEyeBagCoverage(frozen.eye_bag_preset);
      if(disposed||pending||state.result!==frozen||contextGeneration!==capturedContext)return;
      if(!verified){set({message:'去眼袋逐眼保护或完整共享来源成员摘要未通过校验，请重新预检。'});return;}
    }
    if(options.eyeBagPresetAck!==undefined&&action!=='apply'){set({message:'去眼袋预设确认只能用于冻结应用。'});return;}
    const decoration=action==='apply'&&(expectedScope?.includes(DECORATION_OP)||frozen?.face_decoration_visual_required===true||options.faceDecorationPresetAck!==undefined);
    if(decoration){
      const snapshot=state,reviewContext=context.reviewContextKey,capturedGeneration=contextGeneration;
      if(!frozen?.face_decoration_preset||frozen.face_decoration_visual_required!==true||frozen.face_decoration_preset.version===2&&(expectedScope===undefined||JSON.stringify(expectedScope)!==JSON.stringify(frozen.module_scope)||options.eyeBagPresetAck!==undefined)||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==reviewContext||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope??[])||!validDecorationPreset(frozen.face_decoration_preset,context.documentId,frozen.revision,frozen.source_proof)||!sameDecorationPresetAck(options.faceDecorationPresetAck,decorationPresetAck(frozen.face_decoration_preset))){set({message:'请先读取并确认本照片全部所选效果及已有装饰的真实前后图。'});return;}
      const checked=await verifyDecorationPreset(frozen.face_decoration_preset);
      if(!checked||pending||state!==snapshot||contextGeneration!==capturedGeneration||context.reviewContextKey!==reviewContext||disposed){set({message:'装饰审核证据或目标已改变，请重新预检。'});return;}
    }
    if(options.faceDecorationPresetAck!==undefined&&action!=='apply'){set({message:'装饰图像确认只能用于原冻结应用。'});return;}
    const collarbone=action==='apply'&&(expectedScope?.includes(COLLARBONE_PRESET_OP)||frozen?.module_scope?.includes(COLLARBONE_PRESET_OP)||options.collarbonePresetAck!==undefined);
    if(collarbone&&(!frozen?.collarbone_preset||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope?.includes(COLLARBONE_PRESET_OP)||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validCollarbonePreset(frozen.collarbone_preset,context.documentId,frozen.revision,frozen.source_proof)
      ||!sameCollarbonePresetAck(options.collarbonePresetAck,collarbonePresetAck(frozen.collarbone_preset)))){
      set({message:'请先读取并确认当前照片的完整混合预设前后效果，包含归零操作。'});return;
    }
    if(options.collarbonePresetAck!==undefined&&action!=='apply'){set({message:'锁骨预设确认只能用于其冻结应用。'});return;}
    const spill=action==='apply'&&(expectedScope?.includes(SPILL_TRANSFER_OP)||frozen?.module_scope?.includes(SPILL_TRANSFER_OP)||options.spillReviewAck!==undefined);
    if(spill&&(!frozen?.spill_transfer||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope||!frozen.module_scope.includes(SPILL_TRANSFER_OP)||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validSpillTransfer(frozen.spill_transfer,context.documentId,frozen.revision,frozen.applies?.[SPILL_TRANSFER_OP],frozen.source_proof)
      ||!validSpillTransferAck(options.spillReviewAck,[frozen.spill_transfer]))){
      set({message:'请先查看并明确确认当前照片的祛反光前后效果，再应用这次冻结预设。'});return;
    }
    if(options.spillReviewAck!==undefined&&action!=='apply'){
      set({phase:'error',action,result:null,message:'祛反光视觉确认只允许用于已冻结预设的应用。'});return;
    }
    const shadow=action==='apply'&&(expectedScope?.includes(SHADOW_TRANSFER_OP)||frozen?.module_scope?.includes(SHADOW_TRANSFER_OP)||options.shadowReviewAck!==undefined);
    if(shadow&&(!frozen?.shadow_transfer||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope||!frozen.module_scope.includes(SHADOW_TRANSFER_OP)||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validShadowTransfer(frozen.shadow_transfer,context.documentId,frozen.revision,frozen.applies?.[SHADOW_TRANSFER_OP],frozen.source_proof)
      ||!validShadowTransferAck(options.shadowReviewAck,[frozen.shadow_transfer]))){
      set({message:'请先查看并明确确认当前照片的原图阴影前后效果，再应用这次冻结预设。'});return;
    }
    if(options.shadowReviewAck!==undefined&&action!=='apply'){
      set({phase:'error',action,result:null,message:'原图阴影视觉确认只允许用于已冻结预设的应用。'});return;
    }
    const torso=action==='apply'&&(expectedScope?.includes(TORSO_TRANSFER_OP)||frozen?.module_scope?.includes(TORSO_TRANSFER_OP)||options.torsoReviewAck!==undefined);
    if(torso&&(!frozen?.torso_transfer||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope||frozen.module_scope.length!==1||frozen.module_scope[0]!==TORSO_TRANSFER_OP||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validTorsoTransfer(frozen.torso_transfer,context.documentId,frozen.revision,frozen.applies?.[TORSO_TRANSFER_OP],frozen.source_proof)
      ||!validTorsoTransferAck(options.torsoReviewAck,[frozen.torso_transfer])
      ||options.spillReviewAck!==undefined||options.shadowReviewAck!==undefined||options.waistReviewAck!==undefined||options.headReviewAck!==undefined||options.xmpReviewAck!==undefined||options.localMaskTransfer!==undefined)){
      set({message:'请先查看并确认当前目标身体及本人面部的上身长度前后效果，再独立应用这次冻结预设。'});return;
    }
    if(options.torsoReviewAck!==undefined&&action!=='apply'){
      set({phase:'error',action,result:null,message:'上身长度视觉确认只允许用于已冻结预设的应用。'});return;
    }
    const waist=action==='apply'&&(expectedScope?.includes(WAIST_TRANSFER_OP)||frozen?.module_scope?.includes(WAIST_TRANSFER_OP)||options.waistReviewAck!==undefined);
    if(waist&&(!frozen?.waist_transfer||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope||frozen.module_scope.length!==1||frozen.module_scope[0]!==WAIST_TRANSFER_OP||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validWaistTransfer(frozen.waist_transfer,context.documentId,frozen.revision,frozen.applies?.[WAIST_TRANSFER_OP],frozen.source_proof)
      ||!validWaistTransferAck(options.waistReviewAck,[frozen.waist_transfer])
      ||options.spillReviewAck!==undefined||options.shadowReviewAck!==undefined||options.torsoReviewAck!==undefined||options.xmpAck!==undefined||options.headReviewAck!==undefined||options.xmpReviewAck!==undefined||options.localMaskTransfer!==undefined)){
      set({message:'请先查看并确认本目标身体及本人面部的腰长前后效果，再独立应用这次冻结预设。'});return;
    }
    if(options.waistReviewAck!==undefined&&action!=='apply'){
      set({phase:'error',action,result:null,message:'腰长视觉确认只允许用于已冻结预设的应用。'});return;
    }
    const head=action==='apply'&&(expectedScope?.includes(HEAD_TRANSFER_OP)||frozen?.module_scope?.includes(HEAD_TRANSFER_OP)||options.headReviewAck!==undefined);
    if(head&&(!frozen?.head_transfer||!frozen.preflight_token||options.preflightToken!==frozen.preflight_token
      ||options.id!==frozen.id||frozen.document_id!==context.documentId||state.submitted?.reviewContextKey!==context.reviewContextKey
      ||!frozen.module_scope||frozen.module_scope.length!==1||frozen.module_scope[0]!==HEAD_TRANSFER_OP||expectedScope!==undefined&&!sameScope(expectedScope,frozen.module_scope)
      ||!validHeadTransfer(frozen.head_transfer,context.documentId,frozen.revision,frozen.applies?.[HEAD_TRANSFER_OP],frozen.source_proof)
      ||!validHeadTransferAck(options.headReviewAck,[frozen.head_transfer])
      ||options.spillReviewAck!==undefined||options.shadowReviewAck!==undefined||options.waistReviewAck!==undefined||options.torsoReviewAck!==undefined||options.xmpAck!==undefined||options.xmpReviewAck!==undefined||options.localMaskTransfer!==undefined)){
      set({message:'请先查看并确认本目标身体及本人面部的小头前后效果，再独立应用这次冻结预设。'});return;
    }
    if(options.headReviewAck!==undefined&&action!=='apply'){
      set({phase:'error',action,result:null,message:'小头视觉确认只允许用于已冻结预设的应用。'});return;
    }
    const selectedScope=action==='save'?options.moduleScope:expectedScope;
    if(selectedScope?.includes(TORSO_TRANSFER_OP)&&selectedScope.length!==1){set({message:'上身长度必须单独保存、预检与应用，不混合其他模块。'});return;}
    if(selectedScope?.includes(WAIST_TRANSFER_OP)&&(selectedScope.length!==1||options.localMaskTransfer!==undefined||options.xmpExpected!==undefined)){set({message:'腰长必须单独保存、预检与应用，不混合其他模块或审核。'});return;}
    if(selectedScope?.includes(HEAD_TRANSFER_OP)&&(selectedScope.length!==1||options.localMaskTransfer!==undefined||options.xmpExpected!==undefined)){set({message:'小头必须单独保存、预检与应用，不混合其他模块或审核。'});return;}
    if(action==='preflight'&&selectedScope?.includes(HEAD_TRANSFER_OP)&&options.moduleScope!==undefined&&!sameScope(options.moduleScope,selectedScope)){
      set({message:'小头预检的预期作用域与所选预设不一致。'});return;
    }
    if((expectedScope?.includes(SHADOW_TRANSFER_OP)&&expectedScope.some(op=>[SPILL_TRANSFER_OP,'lnx.id_background.v1'].includes(op)))){set({message:'原图阴影标量同步不能与整套背景或祛染同步混用；请分开审核。'});return;}
    const id=uuid(),g=++generation,deadline=now()+(config.timeoutMs??120000);
    // Expected-scope equality only. The engine still loads and validates the
    // stored preset; this field cannot choose or broaden its actual modules.
    const captured={...options,moduleScope:action==='preflight'&&selectedScope?.includes(HEAD_TRANSFER_OP)?[HEAD_TRANSFER_OP]:action==='preflight'&&selectedScope?.includes(COLLARBONE_PRESET_OP)?[...selectedScope]:options.moduleScope?[...options.moduleScope]:undefined,
      ...(options.xmpAck?{xmpAck:{...options.xmpAck,selected:[...options.xmpAck.selected]}}:{}),
      ...(options.xmpReviewAck?{xmpReviewAck:{...options.xmpReviewAck}}:{}),
      ...(options.spillReviewAck?{spillReviewAck:options.spillReviewAck.map(ack=>({...ack}))}:{}),
      ...(options.shadowReviewAck?{shadowReviewAck:options.shadowReviewAck.map(ack=>({...ack}))}:{}),
      ...(options.torsoReviewAck?{torsoReviewAck:options.torsoReviewAck.map(ack=>({...ack}))}:{}),
      ...(options.waistReviewAck?{waistReviewAck:options.waistReviewAck.map(ack=>({...ack}))}:{}),
      ...(options.headReviewAck?{headReviewAck:options.headReviewAck.map(ack=>({...ack}))}:{}),
      ...(options.faceDecorationPresetAck?{faceDecorationPresetAck:structuredClone(options.faceDecorationPresetAck)}:{}),
      ...(options.collarbonePresetAck?{collarbonePresetAck:{...options.collarbonePresetAck}}:{}),
      ...(options.eyeBagPresetAck?{eyeBagPresetAck:structuredClone(options.eyeBagPresetAck)}:{}),
      ...(options.xmpExpected?{xmpExpected:structuredClone(options.xmpExpected)}:{}),
      ...(editing?{documentId:context.documentId}:{}),requestId:id};
    const request:Pending={contextGeneration,id,action,options:captured,expectedScope:expectedScope?[...expectedScope]:undefined,generation:g,...(decoration&&frozen?.face_decoration_preset?{decorationReview:structuredClone(frozen.face_decoration_preset)}:{}),...(eyeBag&&frozen?.eye_bag_preset?{eyeBagReview:structuredClone(frozen.eye_bag_preset)}:{})};pending=request;
    if(request.eyeBagReview?.version===2)setEyeBagPresetAliasWritePending(id,true,request.eyeBagReview.owner.document.epoch);
    if(request.decorationReview?.version===2)setDecorationPresetAliasWritePending(id,true,request.decorationReview.owner.document.epoch);
    set({phase:'working',action,result:null,message:'',submitted:{action,options:captured,requestId:id,reviewContextKey:context.reviewContextKey,...(request.decorationReview?.version===2?{decorationAliasEpoch:request.decorationReview.owner.document.epoch}:{})}});
    try{
      const accepted=await bounded(api.request(action,captured),deadline);
      if(!active(g))return;
      if(!accepted.requested)throw Error('未确认请求入队，不能据此判断未执行');
      await poll(request,deadline);
    }catch(error){uncertain(request,error);}
  }
  async function query(){if(!pending||state.phase!=='uncertain')return;set({phase:'working',result:null,message:''});await poll(pending);}
  function acknowledgeInspection(){
    if(state.phase!=='uncertain')return;
    if(pending?.options.waistReviewAck!==undefined){set({message:'腰长应用结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    if(pending?.options.eyeBagPresetAck!==undefined){set({message:'去眼袋完整预设结果尚未确定，只能查询原请求，不会释放后重复提交。'});return;}
    if(pending?.options.faceDecorationPresetAck!==undefined){set({message:'装饰完整预设写入尚未确定，只能查询原请求，不会释放后重复提交。'});return;}
    if(pending?.options.collarbonePresetAck!==undefined){set({message:'完整预设应用结果尚未确定，只能查询原请求，不会释放后重复提交。'});return;}
    if(pending?.options.headReviewAck!==undefined){set({message:'小头应用结果尚未确定，只能查询原请求；不会释放后重复提交。'});return;}
    generation++;pending=null;set({...initialPresetUi});
  }
  function dismissReview(){if(pending||state.phase==='working'||state.phase==='uncertain')return;set({...initialPresetUi});}
  return {submit,query,acknowledgeInspection,dismissReview,updateContext:(next:PresetContext)=>{const key=JSON.stringify([next.documentId,next.reviewContextKey]);if(key!==contextKey){contextGeneration++;contextKey=key;if(state.action==='preflight'&&!pending)set({result:null});}context={...next};},snapshot:()=>state,
    dispose:()=>{stopWorkspaceRecovery();stopDecorationWorkspaceRecovery();disposed=true;generation++;pending=null;}};
}
