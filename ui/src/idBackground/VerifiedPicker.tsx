import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {invoke} from '@tauri-apps/api/core';
import {createPortal} from 'react-dom';
import {parseCaptureFrame,type VerifiedCapture} from '../captureFrame';
import type {CaptureDescriptor} from '../captureModel';
import {sampleOriginal} from './pickerPort';
import {pickerActions,pickerStages,pickerLabels,type RGB,type PickerMode} from './model';
import type {SelectedSampleReference} from '../sampleLibrary/model';
type SampleProof={document_id:string;capture_id:string;ticket:string;generation:string;recipe_document_id:string;recipe_revision:string};
const pause=()=>new Promise<void>(resolve=>setTimeout(resolve,100));
type Props={documentId:string;mode:PickerMode;reference?:SelectedSampleReference|null;onSample:(r:RGB)=>void;onClose:()=>void};
/** Existing native capture leases verify private file, copied bytes and presented
 * identity. Canvas is for aiming only; samples remain float32 in the engine. */
export function VerifiedPicker({documentId,mode,reference,onSample,onClose}:Props){
 const [frame,setFrame]=useState<VerifiedCapture|null>(null),[eligible,setEligible]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(`正在读取${pickerLabels[mode]}真实浮点输入…`);
 const point=useRef({x:0,y:0});const dialog=useRef<HTMLDivElement|null>(null);
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;return()=>{previous?.focus?.();};},[]);
 const canvas=useRef<HTMLCanvasElement|null>(null),live=useRef(true),serial=useRef(0);
 const capture=useRef({id:crypto.randomUUID().replaceAll('-',''),ticket:null as string|null});
 useEffect(()=>{live.current=true;const c=capture.current;const token=++serial.current;
  void(async()=>{try{
   const arm=await invoke<{ticket:string}>('color_picker_capture',{action:'arm',captureId:c.id,documentId,pickerAction:pickerActions[mode],pickerChannel:'master',...(mode==='reference'?{reference}: {})});c.ticket=arm.ticket;
   if(!live.current||token!==serial.current){await invoke('color_picker_capture',{action:'cancel',captureId:c.id,ticket:c.ticket,documentId});return;}
   const deadline=Date.now()+120000;
   while(live.current&&token===serial.current&&Date.now()<deadline){
    const r=await invoke<{phase:string;descriptor?:CaptureDescriptor;error?:string}>('color_picker_capture_status',{captureId:c.id,ticket:c.ticket});
    if(r.phase==='ready'){
     const d=r.descriptor;if(!d||d.document_id!==documentId||d.capture_id!==c.id||d.ticket!==c.ticket||d.picker_action!==pickerActions[mode]||d.source_stage!==pickerStages[mode]||d.picker_mode!==mode||!d.source_binding)throw Error('原图输入身份不匹配');
     const bytes=await invoke<ArrayBuffer>('color_picker_capture_frame',{captureId:c.id,ticket:c.ticket});
     const verified=parseCaptureFrame(bytes,d,'color-action-input');if(live.current&&token===serial.current)setFrame(verified);return;
    }
    if(['error','stale','idle'].includes(r.phase))throw Error(r.error??'输入画面已失效');await pause();
   }if(live.current)throw Error('原图输入读取超时，请取消后重试');
  }catch(e){if(live.current)setMessage(String(e));}})();
  return()=>{live.current=false;++serial.current;void invoke('color_picker_capture',{action:'cancel',captureId:c.id,ticket:c.ticket,documentId}).catch(()=>{});};
 },[documentId,mode,reference]);
 useLayoutEffect(()=>{if(!frame||!canvas.current)return;let first=0,second=0,valid=true;
  const node=canvas.current;node.width=frame.descriptor.width;node.height=frame.descriptor.height;
  try{const ctx=node.getContext('2d');if(!ctx)throw Error('输入画面画布不可用');ctx.putImageData(new ImageData(frame.rgba,node.width,node.height),0,0);point.current={x:Math.floor(node.width/2),y:Math.floor(node.height/2)};node.focus();
   first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{void(async()=>{try{
    if(!valid||!live.current)return;const r=await invoke<{eligible:boolean}>('color_picker_capture',{action:'presented',captureId:frame.descriptor.capture_id,ticket:frame.descriptor.ticket,documentId});
    if(valid&&live.current){if(!r.eligible)throw Error('输入画面呈现未确认');setEligible(true);setMessage('已锁定真实浮点输入。点击亮显区域取样；暗区不可取样。Esc 取消。');}
   }catch(e){if(valid&&live.current)setMessage(String(e));}})();});});
  }catch(e){setMessage(String(e));}
  return()=>{valid=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
 },[frame,documentId]);
 useEffect(()=>{const key=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.stopPropagation();onClose();}};window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[onClose]);
 async function sample(clientX:number,clientY:number){if(!frame||!canvas.current||!eligible||busy)return;setBusy(true);const d=frame.descriptor,b=canvas.current.getBoundingClientRect();
  try{const x=Math.max(0,Math.min(d.width-1,Math.floor((clientX-b.left)/b.width*d.width))),y=Math.max(0,Math.min(d.height-1,Math.floor((clientY-b.top)/b.height*d.height)));
   if(!d.recipe_document_id||!d.recipe_revision)throw Error('工具输入缺少配方版本');
   const proof:SampleProof={document_id:documentId,capture_id:d.capture_id,ticket:d.ticket,generation:d.generation,recipe_document_id:d.recipe_document_id,recipe_revision:d.recipe_revision};
   const next=await sampleOriginal({...proof,picker_mode:mode,source_binding:d.source_binding,request_id:crypto.randomUUID(),region:{x:Math.max(0,x-2),y:Math.max(0,y-2),width:Math.min(5,d.width-Math.max(0,x-2)),height:Math.min(5,d.height-Math.max(0,y-2))}});
   if(live.current)onSample(next);
  }catch(e){if(live.current)setMessage(String(e));}finally{if(live.current)setBusy(false);}
 }
 return createPortal(<div ref={dialog} className="id-background-picker" onKeyDown={e=>{if(e.key!=='Tab')return;const nodes=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),canvas[tabindex="0"]')??[]);const first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}} role="dialog" aria-modal="true" aria-label="证件照背景真实画面吸管"><div><button type="button" onClick={onClose}>取消取色</button><p>{pickerLabels[mode]} · 经验证的浮点代理画面；暗区是源图边界外或不在审核范围。</p><p role="status">{message}</p><canvas ref={canvas} tabIndex={0} onKeyDown={e=>{if(!frame||!canvas.current)return;const d=frame.descriptor;if(e.key.startsWith("Arrow")){e.preventDefault();point.current={x:Math.max(0,Math.min(d.width-1,point.current.x+(e.key==="ArrowRight"?1:e.key==="ArrowLeft"?-1:0))),y:Math.max(0,Math.min(d.height-1,point.current.y+(e.key==="ArrowDown"?1:e.key==="ArrowUp"?-1:0)))};setMessage(`取样坐标 ${point.current.x}, ${point.current.y}；Enter 确认`);}else if(e.key==="Enter"){e.preventDefault();const b=canvas.current.getBoundingClientRect();void sample(b.left+(point.current.x+.5)/d.width*b.width,b.top+(point.current.y+.5)/d.height*b.height);}}} aria-label="已验证的工具输入；点击选择颜色" onPointerDown={e=>{if(e.button===0)void sample(e.clientX,e.clientY);}} style={{maxWidth:'90vw',maxHeight:'75vh',objectFit:'contain',cursor:eligible?'crosshair':'wait'}}/></div></div>,document.body);
}
