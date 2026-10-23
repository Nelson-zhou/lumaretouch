import {CROP_OP,cropReviewKey} from '../cropTransfer/model';
import {SPILL_TRANSFER_OP,spillTransferReviewKey,spillTransferAck} from '../spillRemoval/transferModel';
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
  const [cropImage,setCropImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [xmpImage,setXmpImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [spillImage,setSpillImage]=useState<{key:string;ready:boolean}>({key:'',ready:false});
  const [xmpImport,setXmpImport]=useState<XmpImportDraft|null>(null);
  const xmpDraft=useRef<XmpImportDraft|null>(null),xmpImportTarget=useRef<{path:string;id?:string}|null>(null);
  const [ui,setUi]=useState<PresetUi>(initialPresetUi),[form,dispatch]=useReducer(presetFormReducer,initialPresetForm);
  const [localMaskTransfer,setLocalMaskTransfer]=useState(defaultMaskTransfer),[saveMaskTransfer,setSaveMaskTransfer]=useState(defaultMaskTransfer);
  useEffect(()=>setLocalMaskTransfer(v=>({...v,groups:null})),[form.selectedId]);
  useEffect(()=>setSaveMaskTransfer(v=>({...v,groups:null})),[context.documentId]);
  const [note,setNote]=useState(''),[dialogBusy,setDialogBusy]=useState(false);
  const latest=useRef({context,catalog,onRefresh,face,form,localMaskTransfer,saveMaskTransfer});latest.current={context,catalog,onRefresh,face,form,localMaskTransfer,saveMaskTransfer};
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
    await current()?.submit('save',{id:`user-${crypto.randomUUID()}`,name:value.form.name.trim(),kind:'custom',moduleScope:[...value.form.scope],localMaskTransfer:value.form.scope.includes(LOCAL_GRADE_OP)?value.saveMaskTransfer:undefined});
  }
  async function apply(id=form.selectedId){
    if(locked())return;const value=latest.current,preset=value.catalog?.list.find(p=>p.id===id);
    if(!preset){setNote('请从当前列表选择预设');return;}
    const ops=Object.keys(preset.modules);
    if(preset.xmp_import!==undefined&&value.catalog?.xmp_import_protocol!==1){setNote('当前引擎未声明 XMP 检查和逐图审核协议，不能应用该预设。');return;}
    if(preset.xmp_import!==undefined&&!validXmpSummary(preset.xmp_import,ops)){setNote('XMP 来源摘要或选择不完整，不能应用；请重新检查导入文件。');return;}
    if(unavailableScope(ops,value.catalog?.modules??[]).length){setNote('这个预设包含当前引擎不可用的模块');return;}
    if(!value.face.ok&&value.catalog?.modules.some(m=>ops.includes(m.operation_id)&&m.single_face)){
      setNote(value.face.why||'这个预设的部分模块需要可用的单脸');return;
    }
    dispatch({type:'select',id});setNote('');
    await current()?.submit(preset.xmp_import||ops.some(op=>[LOCAL_GRADE_OP,OPTICS_AUTO_OP,"lnx.reference_color.v1",CROP_OP,"lnx.spill_removal.v1"].includes(op))?'preflight':'apply',
      {id,...(preset.xmp_import?{xmpExpected:preset.xmp_import}:{}),...(ops.includes(LOCAL_GRADE_OP)?{localMaskTransfer:value.localMaskTransfer}:{})},ops);
  }
  const review=ui.action==='preflight'&&ui.submitted?.reviewContextKey===context.reviewContextKey&&ui.result?.success&&ui.result.id===form.selectedId&&ui.result.document_id===context.documentId
    &&(!ui.result.module_scope?.includes(LOCAL_GRADE_OP)||JSON.stringify(ui.submitted?.options.localMaskTransfer)===JSON.stringify(localMaskTransfer))?ui.result:null;
  const cropKey=review?.crop_transfer&&review.preflight_token?cropReviewKey(review.preflight_token,review.crop_transfer):'';
  const cropReady=!review?.module_scope?.includes(CROP_OP)||!!cropKey&&cropImage.key===cropKey&&cropImage.ready;
  const xmpKey=review?.xmp_transfer&&review.xmp_report&&review.preflight_token?xmpReviewKey(review.preflight_token,review.xmp_transfer,review.xmp_report):'';
  const xmpReady=!selected?.xmp_import&&!review?.xmp_transfer||!!xmpKey&&xmpImage.key===xmpKey&&xmpImage.ready;
  const spillKey=review?.spill_transfer&&review.preflight_token?spillTransferReviewKey(`${review.preflight_token}:${review.request_id}`,review.spill_transfer):'';
  const spillReady=!review?.module_scope?.includes(SPILL_TRANSFER_OP)||!!spillKey&&spillImage.key===spillKey&&spillImage.ready;
  useEffect(()=>setSpillImage({key:'',ready:false}),[spillKey]);
  async function confirmLocal(){
    if(locked()||!cropReady||!xmpReady||!spillReady||!review?.preflight_token||!review.module_scope)return;
    const controller=current();
    if(controller?.snapshot().result?.preflight_token!==review.preflight_token)return;
    const expected=ui.submitted?.options.xmpExpected;
    if(selected?.xmp_import&&(latest.current.catalog?.xmp_import_protocol!==1||!expected||!validXmpSummary(selected.xmp_import,review.module_scope)||selected.xmp_import.source_sha256!==expected.source_sha256
      ||selected.xmp_import.report.report_sha256!==expected.report.report_sha256))return;
    await controller.submit('apply',{id:review.id,preflightToken:review.preflight_token,
      ...(review.module_scope.includes(SPILL_TRANSFER_OP)&&review.spill_transfer?{spillReviewAck:spillTransferAck([review.spill_transfer])}:{}),
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
  async function refresh(){if(locked())return;setNote('');await current()?.submit('list');}
  async function inspect(){try{await latest.current.onRefresh();setNote('已请求当前状态，请核对照片与预设列表；不会重复提交操作。');}catch(error){setNote(String(error));}}
  return {ui,form,note,selected,catalog,context,dialogBusy,face,localMaskTransfer,setLocalMaskTransfer,saveMaskTransfer,setSaveMaskTransfer,review,confirmLocal,cropKey,cropReady,setCropImage,
    spillKey,spillReady,setSpillImage,dismissReview:()=>{setSpillImage({key:'',ready:false});current()?.dismissReview();},
    xmpKey,xmpReady,setXmpImage,xmpImport,cancelXmpImport,confirmXmpImport,
    busy:dialogBusy||!!xmpImport||ui.phase==='working'||ui.phase==='uncertain',
    setName:(value:string)=>dispatch({type:'name',value}),select:(id:string)=>dispatch({type:'select',id}),
    setScope:(ops:string[])=>dispatch({type:'scope',ops:ops.includes(OPTICS_AUTO_OP)&&ops.includes(OPTICS_MANUAL_OP)?ops.filter(op=>op!==(ops[ops.length-1]===OPTICS_MANUAL_OP?OPTICS_AUTO_OP:OPTICS_MANUAL_OP)):ops}),save,apply,importFile,remove,refresh,inspect,
    applyByLabel:(label:string)=>{const list=latest.current.catalog?.list??[];const p=presetFromLabel(label,list);if(!p){setNote('预设标签不存在或有歧义，请在模块预设面板按 ID 选择');return;}return apply(p.id);},
    query:()=>current()?.query(),acknowledgeInspection:()=>flow.current?.acknowledgeInspection()};
}
export type PresetWorkflowBinding=ReturnType<typeof usePresetWorkflow>;
