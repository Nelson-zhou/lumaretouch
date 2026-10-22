import {useCallback,useEffect,useRef,useState} from 'react';
import type {Capture,Context,Mode,Port,Preview,Report,Result,Review,CanvasMask} from './model';
import {message} from './model';
import type {SampleReference} from '../sampleLibrary/model';
export function useSemanticColour(port:Port,documentKey:string,onChanged:()=>void){
 const [context,setContext]=useState<Context|null>(null),[report,setReport]=useState<Report|null>(null),[capture,setCapture]=useState<Capture|null>(null);
 const [review,setReview]=useState<Review|null>(null),[preview,setPreview]=useState<Preview|null>(null),[error,setError]=useState(''),[phase,setPhase]=useState<'idle'|'capturing'|'captured'|'running'|'review'|'committing'|'editing'|'uncertain'>('idle');
 const generation=useRef(0),alive=useRef(true),captureRef=useRef<Capture|null>(null),pendingSession=useRef<string|null>(null);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;generation.current++;void port.request('cancel',{session_id:pendingSession.current}).catch(()=>{});};},[port]);
 const refresh=useCallback(async()=>{const ticket=generation.current;const result=await port.request('state',{}).catch(error=>{if(alive.current&&ticket===generation.current)setError(message(error));throw error;}) as Result;if(alive.current&&ticket===generation.current){
  const frozen=captureRef.current,next=result.context??null;
  if(frozen&&(!next||frozen.context.document_id!==next.document_id||frozen.context.revision!==next.revision)){
   generation.current++;void port.request('cancel',{session_id:frozen.session_id}).catch(()=>{});setCapture(null);captureRef.current=null;setReview(null);setPreview(null);setPhase('idle');setError('目标编辑已变化，待处理的旧拟合已关闭；已应用的颜色配方仍保留。');
  }
  setContext(next);setReport(result.report??null);
 }},[port]);
 useEffect(()=>{generation.current++;setCapture(null);captureRef.current=null;setReview(null);setPreview(null);setPhase('idle');void port.request('cancel',{session_id:pendingSession.current}).catch(()=>{});void refresh().catch(e=>setError(message(e)));},[documentKey,port,refresh]);
 const cancel=useCallback(async()=>{const ticket=++generation.current;try{await port.request('cancel',{session_id:pendingSession.current});if(alive.current&&ticket===generation.current){setPhase('idle');setCapture(null);captureRef.current=null;setReview(null);setPreview(null);}}catch(e){if(alive.current&&ticket===generation.current){setError(message(e));setPhase('uncertain');}}},[port]);
 const freeze=useCallback(async(reference:SampleReference)=>{if(!context)return;const ticket=++generation.current;setError('');setPhase('capturing');setCapture(null);captureRef.current=null;setReview(null);setPreview(null);
  try{const session_id=crypto.randomUUID().replaceAll('-','');pendingSession.current=session_id;const result=await port.request('capture',{reference,context,session_id}) as Capture;if(!alive.current||ticket!==generation.current)return;setCapture(result);captureRef.current=result;setPhase('captured');}
  catch(e){if(alive.current&&ticket===generation.current){setError(message(e));setPhase('idle');}}
 },[context,port]);
 const start=useCallback(async(mode:Mode,strengths:number[],referenceSelection:CanvasMask|null,targetSelection:CanvasMask|null)=>{const c=captureRef.current;if(!c)return;const ticket=++generation.current;setError('');setPhase('running');setReview(null);setPreview(null);
  try{await port.request('start',{session_id:c.session_id,mode,strengths,reference_selection:referenceSelection,target_selection:targetSelection});
   while(alive.current&&ticket===generation.current){await new Promise(r=>setTimeout(r,500));if(!alive.current||ticket!==generation.current)return;const r=await port.request('poll',{session_id:c.session_id}) as Result;if(!alive.current||ticket!==generation.current)return;
    if(r.state==='ready'&&r.review){setReview(r.review);setPreview(r.preview??null);setPhase('review');return;}
    if(r.state==='failed'||r.state==='cancelled')throw new Error(r.error||'追色任务已取消');
   }
  }catch(e){if(alive.current&&ticket===generation.current){setError(message(e));setPhase('captured');}}
 },[port]);
 const commit=useCallback(async()=>{const c=captureRef.current;if(!c||!review)return;const ticket=++generation.current;setPhase('committing');setError('');try{const r=await port.request('commit',{session_id:c.session_id,proof:review.proof,reviewed:true}) as Result;
   if(!alive.current||ticket!==generation.current)return;setReport(r.report??null);setContext(r.context??null);setReview(null);setCapture(null);captureRef.current=null;setPreview(null);setPhase('idle');onChanged();
  }catch(e){if(!alive.current||ticket!==generation.current)return;setError('应用结果需核对：'+message(e));setPhase('uncertain');await refresh().catch(()=>{});}
 },[review,port,onChanged,refresh]);
 const edit=useCallback(async(operation:string,payload:unknown)=>{if(!context)return;const ticket=++generation.current;setPhase('editing');setError('');try{const r=await port.request('edit',{context,operation,payload}) as Result;if(!alive.current||ticket!==generation.current)return;setReport(r.report??null);setContext(r.context??null);setCapture(null);captureRef.current=null;setReview(null);setPreview(null);setPhase('idle');onChanged();}catch(e){if(!alive.current||ticket!==generation.current)return;setError(message(e));setPhase('uncertain');await refresh().catch(()=>{});}},[context,port,onChanged,refresh]);
 return {context,report,capture,review,preview,error,phase,refresh,freeze,start,commit,cancel,edit};
}
