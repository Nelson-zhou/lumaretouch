import {useEffect,useRef,useState} from 'react';
import type {PointerEvent} from 'react';
import {createPortal} from 'react-dom';
import {invoke} from '@tauri-apps/api/core';
import type {LocalMaskOwner} from '../localMasks/useLocalMaskWorkflow';
import {OPERATION_LABELS,type MaskOperation,type PromptSet} from '../localMasks/model';
import {CandidateMask} from './CandidateMask';
import {PromptedModelSetup} from './PromptedModelSetup';
import './promptedMasks.css';
interface Prediction {source_image:string;candidates:string[];scores:number[];model:unknown;input_sha256:string;device:'CPU'|'CUDA'|'ROCm';inference_size:unknown;prompts:PromptSet}
interface Packet {document_id?:string;presented_candidate?:number;preview_id?:string;state?:string;phase?:string;error?:string;result?:Prediction;source_image?:string}
const uuid=()=>crypto.randomUUID().replaceAll('-','');
const empty=():PromptSet=>({points:[],box:null});
/** One immutable preview identity per edit. No late response can replace newer prompts. */
export function PromptedMaskDialog({owner,onClose}:{owner:LocalMaskOwner;onClose:()=>void}){
  const {state,workflow,context}=owner;
  const [source,setSource]=useState(''),[result,setResult]=useState<Prediction|null>(null),[prompts,setPrompts]=useState<PromptSet>(empty);
  const [mode,setMode]=useState<'positive'|'negative'|'box'>('positive'),[device,setDevice]=useState<'cpu'|'cuda'>('cpu');
  const [candidate,setCandidate]=useState(0),[presented,setPresented]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState('正在准备已审核的原始源图…');
  const [name,setName]=useState('AI提示选区'),[operation,setOperation]=useState<MaskOperation>('add'),[opacity,setOpacity]=useState(1),[feather,setFeather]=useState(0);
  const [drag,setDrag]=useState<[number,number,number,number]|null>(null);
  const image=useRef<HTMLImageElement>(null),dialog=useRef<HTMLDivElement>(null),alive=useRef(true),generation=useRef(0),preview=useRef<string|null>(null),opened=useRef(false),submitting=useRef(false);
  const gesture=useRef<{id:number;start:[number,number]}|null>(null);
  const sourceReady=useRef(false),maskReady=useRef(false),raf=useRef<number[]>([]);
  const frame=state.frame?.descriptor,documentKey=useRef(context.documentId+':'+context.contextKey);
  const capture=useRef(frame);if(frame)capture.current=frame;
  const identity=()=>({captureId:capture.current?.capture_id,ticket:capture.current?.ticket});
  const clearPreview=()=>{++generation.current;const old=preview.current;preview.current=null;raf.current.forEach(cancelAnimationFrame);raf.current=[];setResult(null);setPresented(false);setBusy(false);maskReady.current=false;if(old)void invoke('prompted_masks',{action:'cancel',previewId:old,...identity()}).catch(()=>{});};
  const close=()=>{if(!submitting.current){clearPreview();workflow.cancel();}onClose();};
  useEffect(()=>{
    alive.current=true;dialog.current?.focus();
    const blur=()=>close();const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();close();}};
    window.addEventListener('blur',blur);window.addEventListener('keydown',key);
    return()=>{alive.current=false;window.removeEventListener('blur',blur);window.removeEventListener('keydown',key);queueMicrotask(()=>{if(alive.current)return;++generation.current;raf.current.forEach(cancelAnimationFrame);const id=preview.current;preview.current=null;if(id&&!submitting.current)void invoke('prompted_masks',{action:'cancel',previewId:id,...identity()}).catch(()=>{});if(!submitting.current)workflow.cancel();});};
  },[]);
  useEffect(()=>{if(documentKey.current!==context.documentId+':'+context.contextKey||['idle','failure','success','uncertain'].includes(state.phase))close();},[context.documentId,context.contextKey,state.phase]);
  async function receive(id:string,token:number,first:unknown){
    let packet=first as Packet;
    const current=()=>alive.current&&generation.current===token&&preview.current===id;
    while(current()){
      if(packet?.preview_id&&packet.preview_id!==id)throw Error('AI 预览身份不匹配');
      if(packet?.error||['error','failed','cancelled','stale'].includes(packet?.state??packet?.phase??''))throw Error(packet.error||'AI 预览已失效，请重新预测');
      const value=packet?.result;
      if(value&&(packet.preview_id!==id||packet.document_id!==context.documentId||packet.state!=='ready'))throw Error('AI 结果与当前照片或预览不匹配');
      if(value?.candidates?.length&&(!Array.isArray(value.candidates)||value.candidates.length!==3||!value.candidates.every(v=>typeof v==='string'&&v.startsWith('data:image/png;base64,'))||!Array.isArray(value.scores)||value.scores.length!==3))throw Error('AI 候选结果不完整');
      if(value?.source_image){setSource(value.source_image);if(Array.isArray(value.candidates)&&value.candidates.length){setResult(value);setCandidate(0);setPresented(false);setBusy(false);setMessage(`已生成 ${value.candidates.length} 个候选，执行设备 ${value.device}。请选择并检查实际覆盖范围。`);return;}if((packet.state??packet.phase)==='ready'){setBusy(false);setMessage('请在当前来源图添加提示，再点击预测。');return;}}
      if(packet?.source_image){setSource(packet.source_image);setBusy(false);setMessage('请在当前来源图添加提示，再点击预测。');return;}
      await new Promise(resolve=>setTimeout(resolve,250));if(!current())return;
      await invoke('prompted_masks',{action:'poll',previewId:id,...identity()});if(!current())return;
      packet=await invoke<Packet>('prompted_masks_status',{previewId:id});
    }
  }
  async function request(action:'open'|'predict'){
    if(!frame||state.phase!=='target')return;
    clearPreview();const token=generation.current,id=uuid();preview.current=id;setBusy(true);setMessage(action==='open'?'正在读取完整原始源图…':'正在本机预测；不会上传照片。');
    try{const first=await invoke('prompted_masks',{action,previewId:id,captureId:frame.capture_id,ticket:frame.ticket,...(action==='predict'?{prompts,device}:{})});
      if(alive.current&&generation.current===token&&preview.current===id)await receive(id,token,first);
    }catch(error){if(alive.current&&generation.current===token){setBusy(false);setMessage(String(error));}}
  }
  useEffect(()=>{if(state.phase==='target'&&frame&&!opened.current){opened.current=true;void request('open');}},[state.phase,frame]);
  const edit=(next:PromptSet)=>{clearPreview();setPrompts(next);setMessage('提示已改变，旧候选已作废；请重新预测。');};
  // The hit rectangle is the actual contained image, never the padded stage.
  const point=(event:PointerEvent):[number,number]|null=>{const img=image.current;if(!img||!img.naturalWidth)return null;const r=img.getBoundingClientRect();const scale=Math.min(r.width/img.naturalWidth,r.height/img.naturalHeight);const w=img.naturalWidth*scale,h=img.naturalHeight*scale,x=(event.clientX-r.left-(r.width-w)/2)/w,y=(event.clientY-r.top-(r.height-h)/2)/h;return x>=0&&x<=1&&y>=0&&y<=1?[x,y]:null;};
  const boxFrom=(a:[number,number],b:[number,number]):[number,number,number,number]=>[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];
  const acknowledge=()=>{
    if(!sourceReady.current||!maskReady.current||!result||!preview.current)return;
    const id=preview.current,token=generation.current,index=candidate;
    raf.current.forEach(cancelAnimationFrame);
    raf.current=[requestAnimationFrame(()=>{raf.current=[requestAnimationFrame(()=>{
      if(!alive.current||generation.current!==token||preview.current!==id)return;
      void (async()=>{
        const current=()=>alive.current&&generation.current===token&&preview.current===id;
        try{
          await invoke('prompted_masks',{action:'presented',previewId:id,candidate:index,...identity()});
          const deadline=Date.now()+15000;
          while(current()){
            if(Date.now()>deadline)throw Error('候选显示确认超时；请重新选择候选，不会自动应用');
            await invoke('prompted_masks',{action:'poll',previewId:id,...identity()});if(!current())return;
            const packet=await invoke<Packet>('prompted_masks_status',{previewId:id});if(!current())return;
            if(packet.preview_id===id&&packet.presented_candidate===index&&packet.state==='ready'){setPresented(true);return;}
            if(packet.error||['failed','stale','cancelled'].includes(packet.state??''))throw Error(packet.error||'候选已失效');
            await new Promise(resolve=>setTimeout(resolve,200));
          }
        }catch(error){if(current()){setPresented(false);setMessage(String(error));}}
      })();
    })];})];
  };
  const choose=(index:number)=>{++generation.current;raf.current.forEach(cancelAnimationFrame);setPresented(false);if(index===candidate){acknowledge();return;}setCandidate(index);maskReady.current=false;};
  const apply=()=>{
    if(!presented||!preview.current||!result||!name.trim()||submitting.current)return;
    if(workflow.acceptPrompted({action:'accept_prompted',preview_id:preview.current,candidate,id:uuid(),name:name.trim(),operation,opacity,feather})){
      submitting.current=true;void workflow.apply();onClose();
    }
  };
  useEffect(()=>{if(state.phase==='target')dialog.current?.focus();},[state.phase]);
  const displayedBox=drag??prompts.box;
  // Let the existing source overlay actually paint before covering it with this dialog.
  if(state.phase!=='target')return null;
  return createPortal(<div className="promptedBackdrop" data-readonly-scopes onPointerDown={e=>e.stopPropagation()}><div className="promptedDialog" ref={dialog} role="dialog" aria-modal="true" aria-label="AI 提示选区" tabIndex={-1} onKeyDown={event=>{if(event.key!=='Tab')return;const nodes=dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),summary');if(!nodes?.length)return;const first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&(document.activeElement===first||document.activeElement===dialog.current)){event.preventDefault();last.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}}}>
    <header><strong>AI 提示选区</strong><button onClick={close}>取消并关闭</button></header>
    <p>原始源图（未旋转）：不含修补、形变、裁切或调色，不是最终效果图。仅本机处理，不上传照片。显示代理最长边不超过 1024，推理最长边不超过 2048。</p>
    <PromptedModelSetup/>
    {!source&&!busy&&<button disabled={state.phase!=='target'} onClick={()=>void request('open')}>重新读取原始源图</button>}
    <div className="promptedToolbar"><label>提示方式<select value={mode} onChange={e=>{gesture.current=null;setDrag(null);setMode(e.target.value as typeof mode);}}><option value="positive">正点：选中</option><option value="negative">负点：排除</option><option value="box">拖动矩形框</option></select></label>
      <label>推理设备<select value={device} onChange={e=>{clearPreview();setDevice(e.target.value as 'cpu'|'cuda');}}><option value="cpu">CPU</option><option value="cuda">GPU（CUDA / ROCm；需对应运行时）</option></select></label>
      <button disabled={!source||busy||(!prompts.points.length&&!prompts.box)} onClick={()=>void request('predict')}>预测候选</button><button disabled={!prompts.points.length&&!prompts.box} onClick={()=>edit(empty())}>清空提示</button>
    </div>
    {source&&<div className="promptedImageArea"><div className="promptedImageStack"
      onPointerDown={event=>{if(event.button!==0||state.phase!=='target')return;const p=point(event);if(!p)return;event.preventDefault();if(mode==='box'){clearPreview();gesture.current={id:event.pointerId,start:p};setDrag([...p,...p]);event.currentTarget.setPointerCapture(event.pointerId);}else if(prompts.points.length<64)edit({...prompts,points:[...prompts.points,{x:p[0],y:p[1],label:mode==='positive'?1:0}]});else setMessage('最多 64 个点，请先删除已有提示。');}}
      onPointerMove={event=>{const g=gesture.current,p=point(event);if(g&&g.id===event.pointerId&&p)setDrag(boxFrom(g.start,p));}}
      onPointerUp={event=>{const g=gesture.current,p=point(event);gesture.current=null;setDrag(null);if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);if(g&&p){const box=boxFrom(g.start,p);if(box[2]>box[0]&&box[3]>box[1])edit({...prompts,box});}}}
      onPointerCancel={()=>{gesture.current=null;setDrag(null);}} onLostPointerCapture={()=>{gesture.current=null;setDrag(null);}}>
      <img ref={image} className="promptedSource" src={source} alt="未旋转完整原始源图" draggable={false} onLoad={()=>{sourceReady.current=true;setMessage('原始源图已显示；添加提示后可预测。');acknowledge();}} onError={()=>{sourceReady.current=false;setPresented(false);setMessage('原始源图显示失败，请关闭后重试。');}}/>
      {result&&<CandidateMask key={`${preview.current}:${candidate}`} src={result.candidates[candidate]} onPaint={()=>{maskReady.current=true;acknowledge();}} onError={error=>{maskReady.current=false;setPresented(false);setMessage(error);}}/>}
      <svg className="promptedMarkers" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">{displayedBox&&<rect x={displayedBox[0]*1000} y={displayedBox[1]*1000} width={(displayedBox[2]-displayedBox[0])*1000} height={(displayedBox[3]-displayedBox[1])*1000} fill="none" stroke="#ffe272" strokeWidth="3" vectorEffect="non-scaling-stroke"/>}{prompts.points.map((p,i)=><g key={i}><ellipse cx={p.x*1000} cy={p.y*1000} rx="8" ry="8" fill={p.label?'#47f398':'#ff6076'} stroke="#111" strokeWidth="2"/><text x={p.x*1000+12} y={p.y*1000} fill="white" fontSize="18">{i+1}</text></g>)}</svg>
    </div></div>}
    <div className="promptedToolbar" aria-label="提示列表">{prompts.points.map((p,i)=><button key={i} onClick={()=>edit({...prompts,points:prompts.points.filter((_,j)=>j!==i)})} aria-label={`删除${p.label?'正':'负'}点 ${i+1}`}>{p.label?'+':'−'}{i+1} ×</button>)}{prompts.box&&<button onClick={()=>edit({...prompts,box:null})}>删除矩形框 ×</button>}</div>
    {result&&<><div className="promptedToolbar">{result.candidates.map((_,i)=><button key={i} aria-pressed={candidate===i} onClick={()=>choose(i)}>候选 {i+1} · 估计质量 {Number.isFinite(result.scores[i])?result.scores[i].toFixed(3):'未知'}</button>)}</div><small>质量分为模型估计，不是实测准确率；请检查实际覆盖。此功能不识别宠物类别。</small></>}
    <fieldset disabled={busy}><legend>应用为保留对象</legend><label>名称<input maxLength={80} value={name} onChange={e=>setName(e.target.value)}/></label><label>组合<select value={operation} onChange={e=>setOperation(e.target.value as MaskOperation)}>{(Object.keys(OPERATION_LABELS) as MaskOperation[]).map(op=><option key={op} value={op}>{OPERATION_LABELS[op]}</option>)}</select></label><label>不透明度<input type="range" min="0" max="1" step=".01" value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/>{Math.round(opacity*100)}%</label><label>羽化<input type="range" min="0" max="100" value={feather} onChange={e=>setFeather(Number(e.target.value))}/>{feather}</label><button disabled={!presented||!name.trim()||state.phase!=='target'} onClick={apply}>应用选中候选</button></fieldset>
    <p role="status">{message}</p><small>编辑提示会作废旧候选。Esc、窗口失焦、换照片或关闭对话框会取消未应用的预览。</small>
  </div></div>,document.body);
}
