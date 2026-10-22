import {useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {INSPECTION_EDIT_INTENT,notifyInspectionEditIntent} from '../native';
import {settleCurveEdit} from '../curveEditBarrier';
import type {OpticsContext,OpticsImage,OpticsMutation} from './model';
type Phase='idle'|'loading'|'ready'|'applying'|'uncertain'|'failed';
interface View {open:boolean;phase:Phase;image:OpticsImage|null;previewId:string|null;presented:boolean;dirty:boolean;message:string}
const initial=():View=>({open:false,phase:'idle',image:null,previewId:null,presented:false,dirty:false,message:''});
const uuid=()=>crypto.randomUUID().replaceAll('-','');
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function checkImage(v:unknown):OpticsImage{
  if(!object(v)||v.domain!=='post-manual-liquify-pre-crop-normalized'||v.quality!=='proxy-render-srgb8'||
    !['width','height','input_width','input_height'].every(k=>Number.isSafeInteger(v[k])&&Number(v[k])>0&&Number(v[k])<=800)||
    !['before','after','input'].every(k=>typeof v[k]==='string'&&String(v[k]).startsWith('data:image/png;base64,')&&String(v[k]).length<=4*1024*1024)||!object(v.recipe))throw Error('镜头/透视预览不是有效的真实渲染');
  return v as unknown as OpticsImage;
}
function bounded<T>(p:Promise<T>,ms=120000):Promise<T>{let timer:ReturnType<typeof setTimeout>|undefined;return Promise.race([p,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时，请查询原请求')),Math.max(1,ms));})]).finally(()=>{if(timer)clearTimeout(timer);});}
export function useOpticsWorkflow(context:OpticsContext,refresh:()=>Promise<void>,prepare?:()=>void){
  const latest=useRef({context,refresh,prepare});latest.current={context,refresh,prepare};
  const [state,setState]=useState<View>(initial);
  const owner=useMemo(()=>{
    let active=true,view=initial(),session:string|null=null,document='',baseContext='',request:string|null=null,sequence=0,ownIntent=false;
    const publish=(patch:Partial<View>)=>{view={...view,...patch};if(active)setState(view);};
    function cancel(message='已关闭，未应用的镜头/透视修改已丢弃'){
      if(request){publish({open:false,message:'提交结果尚待确认，不会重复发送'});return;}
      const s=session,p=view.previewId;session=null;++sequence;
      if(s&&p)void invoke('optics_preview',{action:'cancel',previewId:p,sessionId:s,documentId:document,mutation:null}).catch(()=>{});
      publish({...initial(),message});
    }
    async function preview(mutation:OpticsMutation){
      if(!session||request||view.phase==='loading')return;
      const s=session,seq=++sequence,p=uuid();publish({phase:'loading',presented:false,previewId:p,message:'正在计算真实镜头/透视效果…'});
      try{
        await bounded(invoke('optics_preview',{action:'preview',previewId:p,sessionId:s,documentId:document,mutation}));
        const deadline=Date.now()+120000;
        while(active&&session===s&&sequence===seq){
          const raw=await bounded(invoke<unknown>('optics_preview_status',{previewId:p}),deadline-Date.now());
          if(session!==s||sequence!==seq)return;
          if(!object(raw)||raw.preview_id!==p||raw.session_id!==s||raw.document_id!==document)throw Error('镜头/透视预览身份变化');
          if(raw.state==='running'){await new Promise(r=>setTimeout(r,60));continue;}
          if(raw.state!=='ready'||raw.success!==true)throw Error(String(raw.error??'镜头/透视预览未完成'));
          publish({phase:'ready',image:checkImage(raw.result),dirty:object(raw.result)&&raw.result.committable===true,message:'预览已计算，确认效果后应用一次；关闭会丢弃尚未应用的修改'});return;
        }
      }catch(error){if(session===s&&sequence===seq)publish({phase:'failed',message:String(error)});}
    }
    async function start(){
      const c=latest.current.context;
      if(session||request)return;
      if(!c.enabled||c.canStart===false||!c.documentId){publish({message:c.reason??'请等待当前照片可编辑'});return;}
      latest.current.prepare?.();await settleCurveEdit();const now=latest.current.context;if(!now.enabled||now.canStart===false||now.documentId!==c.documentId||now.contextKey!==c.contextKey)return;session=uuid();document=c.documentId;baseContext=c.contextKey;
      publish({...initial(),open:true});await preview({action:'view'});
    }
    async function presented(){
      if(!session||!view.previewId||view.phase!=='ready'||view.presented)return;
      const s=session,p=view.previewId;
      try{await bounded(invoke('optics_preview',{action:'presented',previewId:p,sessionId:s,documentId:document,mutation:null}));
        const deadline=Date.now()+10000;
        while(active&&session===s&&view.previewId===p){
          const raw=await bounded(invoke<unknown>('optics_preview_status',{previewId:p}),deadline-Date.now());
          if(!object(raw)||raw.preview_id!==p)throw Error('展示确认已失效');
          if(raw.state==='presented'){publish({presented:true});return;}
          if(raw.state!=='ready')throw Error(String(raw.error??'展示确认失败'));
          await new Promise(r=>setTimeout(r,40));
        }
      }catch(error){if(session===s)publish({phase:'failed',message:String(error)});}
    }
    async function check(){
      const r=request;if(!r)return;
      try{
        const deadline=Date.now()+120000;
        while(active&&request===r){
          const raw=await bounded(invoke<unknown>('optics_result',{requestId:r}),deadline-Date.now());
          if(!object(raw))throw Error('修改回执无效');
          if(raw.request_id!==r)throw Error('修改回执身份变化');
          if(raw.phase==='pending'){await new Promise(resolve=>setTimeout(resolve,60));continue;}
          if(raw.phase!=='done'||!object(raw.result))throw Error('原操作回执未找到，不会重复提交');
          const receipt=raw.result;
          if(receipt.protocol!==1||receipt.action!=='apply'||receipt.request_id!==r||receipt.document_id!==document||receipt.session_id!==session||receipt.preview_id!==view.previewId||typeof receipt.success!=='boolean'||typeof receipt.outcome_unknown!=='boolean')throw Error('修改回执不完整');
          if(receipt.outcome_unknown===true||receipt.requires_reload===true)throw Error(String(receipt.error??'原操作结果仍不确定'));
          if(receipt.success!==true){request=null;session=null;publish({phase:'failed',open:false,message:String(receipt.error??'镜头/透视未应用')});return;}
          if(!object(receipt.history)||![receipt.history.undo_steps,receipt.history.redo_steps].every(n=>Number.isSafeInteger(n)&&Number(n)>=0))throw Error('修改回执缺少撤销历史证据');
          request=null;session=null;publish({...initial(),message:'镜头/透视已应用，可在历史中整步撤销'});try{await latest.current.refresh();}catch{publish({message:'修改已确认，但界面刷新失败，请重新读取照片状态'});}return;
        }
      }catch(error){if(request===r)publish({phase:'uncertain',message:`原操作结果待确认：${String(error)}`});}
    }
    async function apply(){
      if(!session||!view.previewId||view.phase!=='ready'||!view.presented||!view.dirty||request)return;
      await settleCurveEdit();if(!session||latest.current.context.documentId!==document||latest.current.context.contextKey!==baseContext||!latest.current.context.enabled){cancel('照片已变化，请重新打开工具');return;}request=uuid();publish({phase:'applying',message:'正在保存本次镜头/透视修改…'});
      ownIntent=true;try{notifyInspectionEditIntent();}finally{ownIntent=false;}
      try{await bounded(invoke('optics',{requestId:request,previewId:view.previewId,sessionId:session,documentId:document}));}catch{/* Query an uncertain send rather than re-submit. */}
      await check();
    }
    return {start,preview,presented,apply,check,cancel,externalEdit:()=>{if(!ownIntent&&!request)cancel('照片效果变化，镜头/透视预览已失效');},
      context:()=>{const c=latest.current.context;if(session&&!request&&(c.contextKey!==baseContext||c.documentId!==document))cancel('照片或编辑版本已变化，请重新打开工具');},
      activate:()=>{active=true;setState(view);},stop:()=>{active=false;if(!request)cancel();}};
  },[]);
  useLayoutEffect(()=>{owner.activate();return()=>owner.stop();},[owner]);
  useLayoutEffect(()=>owner.context(),[owner,context.contextKey,context.documentId]);
  useEffect(()=>{const edit=()=>owner.externalEdit();window.addEventListener(INSPECTION_EDIT_INTENT,edit);return()=>window.removeEventListener(INSPECTION_EDIT_INTENT,edit);},[owner]);
  return {state,...owner,active:state.open,pending:state.phase==='applying'||state.phase==='uncertain'};
}
export type OpticsOwner=ReturnType<typeof useOpticsWorkflow>;
