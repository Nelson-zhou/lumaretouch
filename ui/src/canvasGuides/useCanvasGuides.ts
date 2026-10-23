import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {awaitReceipt,send,type GuideResult} from './nativePort';
import {emptyGuides,guidePolicy,isReport,type Axis,type GuideModes,type GuideReport,type GuideState} from './model';
interface Context {loadId:string;contextKey:string;report?:GuideReport;center?:[number,number];modes:GuideModes}
interface Pending {id:string;loadId:string;workspace?:string;documentId?:string;mutation:boolean}
export function useCanvasGuides(context:Context,onChanged:()=>Promise<void>){
  const [report,setReport]=useState<GuideReport|null>(null),[pending,setPending]=useState<Pending|null>(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const latest=useRef(context);latest.current=context;
  const current=useRef(report);current.current=report;
  const inflight=useRef(false),unresolved=useRef<Pending|null>(null),mounted=useRef(true),refresh=useRef(onChanged);refresh.current=onChanged;
  const policy=guidePolicy(context.modes);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  useLayoutEffect(()=>{
    const p=context.report;
    if(isReport(p)&&p.load_id===context.loadId){
      setReport(old=>old?.workspace===p.workspace&&old.document_id===p.document_id&&old.revision>p.revision?old:p);
      const old=unresolved.current;
      if(old?.workspace&&old.workspace!==p.workspace&&!inflight.current){
        unresolved.current=null;setPending(null);setMessage('已切换到新的工程会话。旧参考线操作结果未知，未重发；当前显示新会话的真实状态。');
      }
    }
    else setReport(null);
  },[context.loadId,context.report]);
  function accept(r:GuideResult,op:Pending){
    if(!r.success)throw Error(r.error||'参考线操作未完成');
    const p=r.canvas_guides!;
    if(p.load_id!==op.loadId||(op.workspace&&p.workspace!==op.workspace)||(op.documentId&&p.document_id!==op.documentId))throw Error('参考线回执不属于发起操作的文档');
    if(latest.current.loadId===p.load_id){setReport(p);setMessage(op.mutation?'参考线已更新。保存工程可保留；照片像素未改变。':'已读取参考线');}
  }
  async function run(action:'state'|'set'|'undo'|'redo',state?:GuideState){
    if(inflight.current||unresolved.current)return;
    const ctx=latest.current,p=current.current,mutation=action!=='state';
    const gate=guidePolicy(ctx.modes);
    const moving=action==='undo'||action==='redo'||(action==='set'&&!!state&&!!p&&state.lines.some(line=>p.lines.some(old=>old.id===line.id&&old.position!==line.position)));
    if(!ctx.modes.available||(mutation&&(gate.hidden||ctx.modes.busy||(moving&&(ctx.modes.manual||ctx.modes.repair))||!p||p.load_id!==ctx.loadId)))return;
    const op:Pending={id:crypto.randomUUID(),loadId:ctx.loadId,workspace:p?.workspace,documentId:p?.document_id,mutation};
    inflight.current=true;unresolved.current=op;setBusy(true);setPending(op);setMessage('');
    try{
      await send({action,request_id:op.id,...(mutation?{document_id:p!.document_id,workspace:p!.workspace,revision:p!.revision,load_id:p!.load_id,geometry:p!.geometry,...(action==='set'?{state}:{})}:{})});
      const r=await awaitReceipt(op.id);
      // A definitive rejection is not uncertain and may be corrected after readback.
      unresolved.current=null;if(mounted.current)setPending(null);
      if(mounted.current)accept(r,op);
      if(mutation)await refresh.current();
    }catch(error){if(mounted.current)setMessage(String(error));}
    finally{inflight.current=false;if(mounted.current)setBusy(false);}
  }
  async function query(){
    const op=unresolved.current;if(!op||inflight.current)return;
    inflight.current=true;setBusy(true);
    try{const r=await awaitReceipt(op.id);unresolved.current=null;setPending(null);accept(r,op);await refresh.current();}
    catch(error){setMessage(String(error));}finally{inflight.current=false;setBusy(false);}
  }
  const shown=report?.load_id===context.loadId?report:null;
  const state:GuideState=shown??emptyGuides;
  const change=(next:GuideState)=>{void run('set',next);};
  const owner={documentId:context.loadId,geometry:shown?.geometry??null,state,hidden:policy.hidden,locked:policy.locked||!shown,pending:busy||!!pending,
    contextKey:JSON.stringify([context.contextKey,shown?.workspace,shown?.document_id,shown?.revision,policy.hidden,policy.locked]),
    move:(id:string,position:number)=>change({...state,lines:state.lines.map(x=>x.id===id?{...x,position:Math.max(0,Math.min(1,position))}:x)}),
    remove:(id:string)=>change({...state,lines:state.lines.filter(x=>x.id!==id)}),clear:()=>change({...state,lines:[]}),
    add:(axis:Axis)=>{if(state.lines.length>=128){setMessage('每张照片最多 128 条参考线，请先删除不再需要的参考线');return;}change({visible:true,lines:[...state.lines,{id:crypto.randomUUID(),axis,position:context.center?.[axis==='vertical'?0:1]??.5}]});},
    toggle:()=>change({...state,visible:!state.visible}),undo:()=>{void run('undo');},redo:()=>{void run('redo');},
    read:()=>{void run('state');},query:()=>{void query();},unresolved:!!pending,working:busy,message,reason:policy.reason,
    canManage:!policy.hidden&&!context.modes.busy&&!!shown,canUndo:!!shown?.undo_steps,canRedo:!!shown?.redo_steps};
  const shortcuts=useRef(owner);shortcuts.current=owner;
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{const o=shortcuts.current,target=e.target as HTMLElement|null;
      if(e.key.toLowerCase()!=='r'||e.repeat||e.altKey||!o.canManage||o.pending||target?.isContentEditable||target?.closest('input,textarea,select,[role="dialog"]'))return;
      e.preventDefault();if(e.shiftKey&&!e.ctrlKey&&!e.metaKey)o.toggle();else if(!e.shiftKey)o.add(e.ctrlKey||e.metaKey?'vertical':'horizontal');};
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[]);
  return owner;
}
export type GuideOwner=ReturnType<typeof useCanvasGuides>;
