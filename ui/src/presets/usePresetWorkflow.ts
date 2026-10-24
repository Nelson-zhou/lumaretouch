import {EYE_BAG_PRESET_OP,eyeBagPresetKey,eyeBagPresetAck,neutralEyeBagPreset} from '../eyeBagPreserve/presetModel';
import {COLLARBONE_PRESET_OP,collarbonePresetKey,collarbonePresetAck} from '../collarbone/presetModel';
import {CROP_OP,cropReviewKey} from '../cropTransfer/model';
import {SPILL_TRANSFER_OP,spillTransferReviewKey,spillTransferAck} from '../spillRemoval/transferModel';
import {SHADOW_TRANSFER_OP,shadowTransferReviewKey,shadowTransferAck} from '../originalShadow/transferModel';
import {TORSO_TRANSFER_OP,torsoTransferReviewKey,torsoTransferAck} from '../torsoLength/transferModel';
import {WAIST_TRANSFER_OP,waistTransferReviewKey,waistTransferAck} from '../waistLength/transferModel';
import {HEAD_TRANSFER_OP,headTransferReviewKey,headTransferAck} from '../headSize/transferModel';
import {OPTICS_AUTO_OP,OPTICS_MANUAL_OP} from '../optics/transferReviewModel';
import {defaultMaskTransfer,LOCAL_GRADE_OP} from '../localMasks/transfer';
import {useEffect,useReducer,useRef,useState} from 'react';
import {confirm,open} from '@tauri-apps/plugin-dialog';
import {runPreset,readPresetResult,type PresetState} from '../native';
import {createPresetWorkflow,initialPresetUi,type PresetContext,type PresetUi} from './presetWorkflow';
import {initialPresetForm,presetFormReducer,presetFromLabel,unavailableScope} from './presetModel';
import {validXmpAck,validXmpSummary,xmpReviewAck,xmpReviewKey,type XmpAck,type XmpReport} from '../xmpImport/model';
type XmpImportDraft={path:string;id?:string;report:XmpReport};
export function usePresetWorkflow(context:PresetContext,catalog:PresetState|null,onRefresh:()=>Promise<void>,face:{ok:boolean;why:string}){
  const [eyeBagReplaceLegacy,setEyeBagReplaceLegacy]=useState<boolean|null>(null);
  const [eyeBagImage,setEyeBagImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [cropImage,setCropImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [xmpImage,setXmpImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [spillImage,setSpillImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [shadowImage,setShadowImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [torsoImage,setTorsoImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [waistImage,setWaistImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [collarboneImage,setCollarboneImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [headImage,setHeadImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [xmpImport,setXmpImport]=useState<XmpImportDraft|null>(null);
  const xmpDraft=useRef<XmpImportDraft|null>(null),xmpImportTarget=useRef<{path:string;id?:string}|null>(null);
  const [ui,setUi]=useState<PresetUi>(initialPresetUi),[form,dispatch]=useReducer(presetFormReducer,initialPresetForm);
  const [localMaskTransfer,setLocalMaskTransfer]=useState(defaultMaskTransfer),[saveMaskTransfer,setSaveMaskTransfer]=useState(defaultMaskTransfer);
  useEffect(()=>setLocalMaskTransfer(v=>({...v,groups:null})),[form.selectedId]);
  useEffect(()=>setSaveMaskTransfer(v=>({...v,groups:null})),[context.documentId]);
  const [note,setNote]=useState(''),[dialogBusy,setDialogBusy]=useState(false);
  const latest=useRef({context,catalog,onRefresh,face,form,localMaskTransfer,saveMaskTransfer,eyeBagReplaceLegacy});latest.current={context,catalog,onRefresh,face,form,localMaskTransfer,saveMaskTransfer,eyeBagReplaceLegacy};
  const flow=useRef<ReturnType<typeof createPresetWorkflow>|null>(null),dialogLock=useRef(false),savedRevision=useRef(0);
  useEffect(()=>{
    let live=true,reported='';
    const controller=createPresetWorkflow({request:runPreset,read:readPresetResult},state=>{
      if(!live)return;setUi(state);
      const result=state.result;
      if(result&&reported!==result.request_id){
        reported=result.request_id;
        if(result.success&&result.id){
          if(result.action==='save')dispatch({type:'saved',id:result.id,nameRevision:savedRevision.current});
          if(result.action==='import')dispatch({type:'imported',id:result.id});
          if(result.action==='delete')dispatch({type:'deleted',id:result.id});
        }
        const importTarget=xmpImportTarget.current;
        if(result.success&&result.action==='xmp_inspect'&&result.xmp_report&&importTarget&&result.path===importTarget.path){
          const draft={...importTarget,report:result.xmp_report};xmpDraft.current=draft;setXmpImport(draft);
        }
        // A read-only preflight must not request session_state: that advances
        // the host view revision and would invalidate its own visual review.
        // Mutations still fetch fresh state, never install receipt.doc_state.
        if(result.action!=='preflight'&&result.action!=='xmp_inspect')void Promise.resolve().then(()=>latest.current.onRefresh()).catch(error=>{if(live&&controller.snapshot().result?.request_id===result.request_id)setNote(`操作结果保持不变，但界面刷新失败：${String(error)}`);});
      }
    });
    flow.current=controller;controller.updateContext(latest.current.context);
    return()=>{live=false;flow.current=null;controller.dispose();};
  },[]);
  useEffect(()=>{setEyeBagReplaceLegacy(null);setEyeBagImage({key:'',ready:false});},[form.selectedId,context.documentId]);
  const contextKey=JSON.stringify(context);
  useEffect(()=>{flow.current?.updateContext(context);},[contextKey]);
  const current=()=>{flow.current?.updateContext(latest.current.context);return flow.current;};
  const locked=()=>dialogLock.current||!!xmpDraft.current||['working','uncertain'].includes(flow.current?.snapshot().phase??'');
  const selected=catalog?.list.find(p=>p.id===form.selectedId);
  async function save(){
    if(locked())return;const value=latest.current;
    const missing=unavailableScope(value.form.scope,value.catalog?.modules??[]);
    if(missing.length){setNote('有已不可用的模块，请取消这些选择后再保存');return;}
    savedRevision.current=value.form.nameRevision;setNote('');
    if(value.form.scope.includes(TORSO_TRANSFER_OP)&&value.form.scope.length!==1){setNote('请单独保存上身长度标量，不与其他模块混合。');return;}
    if(value.form.scope.includes(WAIST_TRANSFER_OP)&&value.form.scope.length!==1){setNote('请单独保存腰长标量，不与其他模块混合。');return;}
    if(value.form.scope.includes(HEAD_TRANSFER_OP)&&value.form.scope.length!==1){setNote('请单独保存小头标量，不与其他模块混合。');return;}
    if(value.form.scope.includes(SHADOW_TRANSFER_OP)&&value.form.scope.some(op=>[SPILL_TRANSFER_OP,'lnx.id_background.v1'].includes(op))){setNote('请将原图阴影与祛染、整套背景分开保存，目标需分别审核。');return;}
    await current()?.submit('save',{id:`user-${crypto.randomUUID()}`,name:value.form.name.trim(),kind:'custom',moduleScope:[...value.form.scope],localMaskTransfer:value.form.scope.includes(LOCAL_GRADE_OP)?value.saveMaskTransfer:undefined});
  }
  async function apply(id=form.selectedId){
    if(locked())return;const value=latest.current,preset=value.catalog?.list.find(p=>p.id===id);
    if(!preset){setNote('请从当前列表选择预设');return;}
    const ops=Object.keys(preset.modules);
    const eyeBagNeutral=ops.includes(EYE_BAG_PRESET_OP)&&neutralEyeBagPreset(preset.modules[EYE_BAG_PRESET_OP]),eyeBagActive=ops.includes(EYE_BAG_PRESET_OP)&&!eyeBagNeutral;
    if(eyeBagActive&&ops.includes(COLLARBONE_PRESET_OP)){setNote('去眼袋与锁骨的独立审核暂不合并，请拆分预设。');return;}
    if(eyeBagActive&&typeof value.eyeBagReplaceLegacy!=='boolean'){dispatch({type:'select',id});setNote('请在预设面板明确选择是否替换目标旧版去眼袋，再预检。');return;}
    if(ops.includes(TORSO_TRANSFER_OP)&&ops.length!==1){setNote('此预设混合了上身长度与其他模块，请拆分为独立预设。');return;}
    if(ops.includes(WAIST_TRANSFER_OP)&&(ops.length!==1||preset.xmp_import!==undefined)){setNote('腰长只接受独立标量预设，不混入其他模块或 XMP 审核。');return;}
    if(ops.includes(HEAD_TRANSFER_OP)&&(ops.length!==1||preset.xmp_import!==undefined)){setNote('小头只接受独立标量预设，不混入其他模块或 XMP 审核。');return;}
    if(preset.xmp_import!==undefined&&value.catalog?.xmp_import_protocol!==1){setNote('当前引擎未声明 XMP 检查和逐图审核协议，不能应用该预设。');return;}
    if(preset.xmp_import!==undefined&&!validXmpSummary(preset.xmp_import,ops)){setNote('XMP 来源摘要或选择不完整，不能应用；请重新检查导入文件。');return;}
    if(ops.includes(SHADOW_TRANSFER_OP)&&ops.some(op=>[SPILL_TRANSFER_OP,'lnx.id_background.v1'].includes(op))){setNote('此预设混合了原图阴影与祛染或整套背景，请拆分为独立预设并分别审核。');return;}
    if(unavailableScope(ops,value.catalog?.modules??[]).length){setNote('这个预设包含当前引擎不可用的模块');return;}
    if(!value.face.ok&&value.catalog?.modules.some(m=>ops.includes(m.operation_id)&&m.single_face)){
      setNote(value.face.why||'这个预设的部分模块需要可用的单脸');return;
    }
    dispatch({type:'select',id});setNote('');
    const action=eyeBagActive||preset.xmp_import||ops.some(op=>[LOCAL_GRADE_OP,OPTICS_AUTO_OP,"lnx.reference_color.v1",CROP_OP,"lnx.spill_removal.v1",SHADOW_TRANSFER_OP,TORSO_TRANSFER_OP,WAIST_TRANSFER_OP,HEAD_TRANSFER_OP,COLLARBONE_PRESET_OP].includes(op))?'preflight':'apply';
    await current()?.submit(action,
      {id,...(eyeBagActive?{eyeBagReplaceLegacy:value.eyeBagReplaceLegacy as boolean}:eyeBagNeutral?{eyeBagNeutral:true}:{}),...(action==='preflight'?(ops.includes(HEAD_TRANSFER_OP)?{moduleScope:[HEAD_TRANSFER_OP]}:ops.some(op=>[COLLARBONE_PRESET_OP,EYE_BAG_PRESET_OP].includes(op))?{moduleScope:[...ops]}:{}):{}),...(preset.xmp_import?{xmpExpected:preset.xmp_import}:{}),...(ops.includes(LOCAL_GRADE_OP)?{localMaskTransfer:value.localMaskTransfer}:{})},ops);
  }
  const review=ui.action==='preflight'&&ui.submitted?.reviewContextKey===context.reviewContextKey&&ui.result?.success&&ui.result.id===form.selectedId&&ui.result.document_id===context.documentId
    &&(!ui.result.eye_bag_preset||ui.submitted?.options.eyeBagReplaceLegacy===eyeBagReplaceLegacy)
    &&(!ui.result.module_scope?.includes(LOCAL_GRADE_OP)||JSON.stringify(ui.submitted?.options.localMaskTransfer)===JSON.stringify(localMaskTransfer))?ui.result:null;
  const cropKey=review?.crop_transfer&&review.preflight_token?cropReviewKey(review.preflight_token,review.crop_transfer):'';
  const cropReady=!review?.module_scope?.includes(CROP_OP)||!!cropKey&&cropImage.key===cropKey&&cropImage.ready;
  const xmpKey=review?.xmp_transfer&&review.xmp_report&&review.preflight_token?xmpReviewKey(review.preflight_token,review.xmp_transfer,review.xmp_report):'';
  const xmpReady=!selected?.xmp_import&&!review?.xmp_transfer||!!xmpKey&&xmpImage.key===xmpKey&&xmpImage.ready;
  const spillKey=review?.spill_transfer&&review.preflight_token?spillTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.spill_transfer):'';
  const spillReady=!review?.module_scope?.includes(SPILL_TRANSFER_OP)||!!spillKey&&spillImage.key===spillKey&&spillImage.ready;
  useEffect(()=>setSpillImage({key:'',ready:false}),[spillKey]);
  const shadowKey=review?.shadow_transfer&&review.preflight_token?shadowTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.shadow_transfer):'';
  const shadowReady=!review?.module_scope?.includes(SHADOW_TRANSFER_OP)||!!shadowKey&&shadowImage.key===shadowKey&&shadowImage.ready;
  useEffect(()=>setShadowImage({key:'',ready:false}),[shadowKey]);
  const torsoKey=review?.torso_transfer&&review.preflight_token?torsoTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.torso_transfer):'';
  const torsoReady=!review?.module_scope?.includes(TORSO_TRANSFER_OP)||!!torsoKey&&torsoImage.key===torsoKey&&torsoImage.ready;
  useEffect(()=>setTorsoImage({key:'',ready:false}),[torsoKey]);
  const waistKey=review?.waist_transfer&&review.preflight_token?waistTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.waist_transfer):'';
  const waistReady=!review?.module_scope?.includes(WAIST_TRANSFER_OP)||!!waistKey&&waistImage.key===waistKey&&waistImage.ready;
  useEffect(()=>setWaistImage({key:'',ready:false}),[waistKey]);
  const headKey=review?.head_transfer&&review.preflight_token?headTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.head_transfer):'';
  const headReady=!review?.module_scope?.includes(HEAD_TRANSFER_OP)||!!headKey&&headImage.key===headKey&&headImage.ready;
  useEffect(()=>setHeadImage({key:'',ready:false}),[headKey]);
  const collarboneKey=review?.collarbone_preset&&review.preflight_token&&review.id?collarbonePresetKey(review.preflight_token,review.request_id,review.id,review.collarbone_preset):'';
  const collarboneReady=!review?.module_scope?.includes(COLLARBONE_PRESET_OP)||!!collarboneKey&&collarboneImage.key===collarboneKey&&collarboneImage.ready;
  useEffect(()=>setCollarboneImage({key:'',ready:false}),[collarboneKey]);
  const eyeBagKey=review?.eye_bag_preset&&review.preflight_token&&review.id?eyeBagPresetKey(review.preflight_token,review.request_id,review.id,review.eye_bag_preset):'';
  const eyeBagReady=!review?.eye_bag_preset||!!eyeBagKey&&eyeBagImage.key===eyeBagKey&&eyeBagImage.ready;
  useEffect(()=>setEyeBagImage({key:'',ready:false}),[eyeBagKey]);
  async function confirmLocal(){
    if(locked()||!eyeBagReady||!cropReady||!xmpReady||!spillReady||!shadowReady||!torsoReady||!waistReady||!headReady||!collarboneReady||!review?.preflight_token||!review.module_scope)return;
    const controller=current();
    if(controller?.snapshot().result?.preflight_token!==review.preflight_token)return;
    const expected=ui.submitted?.options.xmpExpected;
    if(selected?.xmp_import&&(latest.current.catalog?.xmp_import_protocol!==1||!expected||!validXmpSummary(selected.xmp_import,review.module_scope)||selected.xmp_import.source_sha256!==expected.source_sha256
      ||selected.xmp_import.report.report_sha256!==expected.report.report_sha256))return;
    await controller.submit('apply',{id:review.id,preflightToken:review.preflight_token,
      ...(review.module_scope.includes(EYE_BAG_PRESET_OP)&&!review.eye_bag_preset&&neutralEyeBagPreset(review.applies?.[EYE_BAG_PRESET_OP])?{eyeBagNeutral:true}:{}),
      ...(review.module_scope.includes(EYE_BAG_PRESET_OP)&&review.eye_bag_preset?{eyeBagPresetAck:eyeBagPresetAck(review.eye_bag_preset)}:{}),
      ...(review.module_scope.includes(SPILL_TRANSFER_OP)&&review.spill_transfer?{spillReviewAck:spillTransferAck([review.spill_transfer])}:{}),
      ...(review.module_scope.includes(SHADOW_TRANSFER_OP)&&review.shadow_transfer?{shadowReviewAck:shadowTransferAck([review.shadow_transfer])}:{}),
      ...(review.module_scope.includes(TORSO_TRANSFER_OP)&&review.torso_transfer?{torsoReviewAck:torsoTransferAck([review.torso_transfer])}:{}),
      ...(review.module_scope.includes(WAIST_TRANSFER_OP)&&review.waist_transfer?{waistReviewAck:waistTransferAck([review.waist_transfer])}:{}),
      ...(review.module_scope.includes(HEAD_TRANSFER_OP)&&review.head_transfer?{headReviewAck:headTransferAck([review.head_transfer])}:{}),
      ...(review.module_scope.includes(COLLARBONE_PRESET_OP)&&review.collarbone_preset?{collarbonePresetAck:collarbonePresetAck(review.collarbone_preset)}:{}),
      ...(expected&&review.xmp_transfer&&review.xmp_report?{xmpExpected:expected,xmpReviewAck:xmpReviewAck(review.xmp_transfer,review.xmp_report)}:{})},review.module_scope);
  }
  async function importFile(asCopy=false,xmp=false){
    if(xmp&&latest.current.catalog?.xmp_import_protocol!==1){setNote('需要支持 XMP 检查与逐图审核的配套引擎。');return;}
    if(locked())return;dialogLock.current=true;setDialogBusy(true);setNote('');
    try{
      const path=await open({title:xmp?'检查 XMP 参数兼容性':asCopy?'导入为新预设副本':'导入预设',multiple:false,
        filters:[{name:xmp?'原始 XMP / 含 XMP 来源的便携 JSON':'LumaRetouch 预设',extensions:xmp?['xmp','json']:['json']}]});
      if(typeof path==='string'&&path){
        if(xmp){xmpImportTarget.current={path,...(asCopy?{id:`user-${crypto.randomUUID()}`}:{})};await current()?.submit('xmp_inspect',{path});}
        else await current()?.submit('import',{path,...(asCopy?{id:`user-${crypto.randomUUID()}`}:{})});
      }
    }catch(error){setNote(`打开导入对话框失败：${String(error)}`);}
    finally{dialogLock.current=false;setDialogBusy(false);}
  }
  function cancelXmpImport(){xmpDraft.current=null;xmpImportTarget.current=null;setXmpImport(null);}
  async function confirmXmpImport(ack:XmpAck){
    const draft=xmpDraft.current,controller=current();
    if(!draft||!controller||['working','uncertain'].includes(controller.snapshot().phase)||!validXmpAck(ack,draft.report))return;
    if(latest.current.catalog?.xmp_import_protocol!==1){setNote('引擎能力已变化，请关闭检查并重新连接配套引擎。');return;}
    cancelXmpImport();setNote('');
    await controller.submit('import',{path:draft.path,...(draft.id?{id:draft.id}:{}),xmpAck:ack});
  }
  async function remove(){
    if(locked())return;const preset=latest.current.catalog?.list.find(p=>p.id===latest.current.form.selectedId);
    if(!preset||preset.builtin)return;
    dialogLock.current=true;setDialogBusy(true);setNote('');
    try{
      const approved=await confirm(`将预设“${preset.name}”移入回收站？\nID：${preset.id}\n配方和素材保留；可在分类管理的回收站恢复，不撤销照片上的调整。`,{title:'移入预设回收站',kind:'warning'});
      if(approved)await current()?.submit('delete',{id:preset.id});
    }catch(error){setNote(`打开删除确认失败：${String(error)}`);}
    finally{dialogLock.current=false;setDialogBusy(false);}
  }
  function changeEyeBagReplaceLegacy(value:boolean|null){
    if(locked()||value===latest.current.eyeBagReplaceLegacy)return;
    // A policy round trip must not resurrect an old frozen token or image ACK.
    current()?.dismissReview();setEyeBagImage({key:'',ready:false});
    latest.current.eyeBagReplaceLegacy=value;setEyeBagReplaceLegacy(value);
  }
  async function refresh(){if(locked())return;setNote('');await current()?.submit('list');}
  async function inspect(){try{await latest.current.onRefresh();setNote('已请求当前状态，请核对照片与预设列表；不会重复提交操作。');}catch(error){setNote(String(error));}}
  return {eyeBagReplaceLegacy,setEyeBagReplaceLegacy:changeEyeBagReplaceLegacy,eyeBagKey,eyeBagReady,setEyeBagImage,ui,form,note,selected,catalog,context,dialogBusy,face,localMaskTransfer,setLocalMaskTransfer,saveMaskTransfer,setSaveMaskTransfer,review,confirmLocal,cropKey,cropReady,setCropImage,
    collarboneKey,collarboneReady,setCollarboneImage,headKey,headReady,setHeadImage,waistKey,waistReady,setWaistImage,torsoKey,torsoReady,setTorsoImage,shadowKey,shadowReady,setShadowImage,spillKey,spillReady,setSpillImage,dismissReview:()=>{setEyeBagImage({key:'',ready:false});setCollarboneImage({key:'',ready:false});setSpillImage({key:'',ready:false});setShadowImage({key:'',ready:false});setTorsoImage({key:'',ready:false});setWaistImage({key:'',ready:false});setHeadImage({key:'',ready:false});current()?.dismissReview();},
    xmpKey,xmpReady,setXmpImage,xmpImport,cancelXmpImport,confirmXmpImport,
    busy:dialogBusy||!!xmpImport||ui.phase==='working'||ui.phase==='uncertain',
    setName:(value:string)=>dispatch({type:'name',value}),select:(id:string)=>dispatch({type:'select',id}),
    setScope:(ops:string[])=>dispatch({type:'scope',ops:ops.includes(OPTICS_AUTO_OP)&&ops.includes(OPTICS_MANUAL_OP)?ops.filter(op=>op!==(ops[ops.length-1]===OPTICS_MANUAL_OP?OPTICS_AUTO_OP:OPTICS_MANUAL_OP)):ops}),save,apply,importFile,remove,refresh,inspect,
    applyByLabel:(label:string)=>{const list=latest.current.catalog?.list??[];const p=presetFromLabel(label,list);if(!p){setNote('预设标签不存在或有歧义，请在模块预设面板按 ID 选择');return;}return apply(p.id);},
    query:()=>current()?.query(),acknowledgeInspection:()=>flow.current?.acknowledgeInspection()};
}
export type PresetWorkflowBinding=ReturnType<typeof usePresetWorkflow>;
