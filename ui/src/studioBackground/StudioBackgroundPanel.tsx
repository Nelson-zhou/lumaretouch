import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {TARGETS,control,neutral,proposal,type Brush,type Parameters,type Proposal,type Report,type Target} from './model';
import type {StudioOwner} from './useStudioBackgroundWorkflow';
import {StudioCanvas} from './StudioCanvas';
import './studioBackground.css';
export function StudioBackgroundPanel({owner,report,disabled=false}:{owner:StudioOwner;report?:Report;disabled?:boolean}){
 const {state,workflow}=owner,[draft,setDraft]=useState<Proposal>(neutral),[brush,setBrush]=useState<Brush>({target:'background',operation:'add',size:12,feather:50,flow:100,opacity:100});
 const [showMask,setShowMask]=useState(true),[before,setBefore]=useState(false),[loaded,setLoaded]=useState<string[]>([]);
 const wasOpen=useRef(false),dirtySerial=useRef(0),sentSerial=useRef(0),draftRef=useRef(draft);draftRef.current=draft;
 useEffect(()=>{if(state.open&&!wasOpen.current){setDraft(proposal(report));dirtySerial.current=0;sentSerial.current=0;setBefore(false);}wasOpen.current=state.open;},[state.open,report]);
 useLayoutEffect(()=>{const im=state.image,id=state.previewId;if(!im||!id||state.phase!=='ready'||before||![im.before,im.after,im.source,im.mask].every(s=>loaded.includes(s)))return;
  let live=true,second=0;const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{if(live)void workflow.presented(id);});});return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
 },[state.image,state.previewId,state.phase,before,loaded,workflow]);
 useEffect(()=>{if(!state.open)return;const key=(e:KeyboardEvent)=>{
  const node=e.target as HTMLElement|null;if(e.key.toLowerCase()!=='b'||e.ctrlKey||e.metaKey||e.altKey||node?.isContentEditable||['INPUT','TEXTAREA','SELECT'].includes(node?.tagName??''))return;
  e.preventDefault();const p=draftRef.current.parameters;
  const next:Target=p.intrusions?'recover_intrusions':p.blemish_background||p.blemish_floor?'recover_blemishes':p.uniformity?'recover_uniformity':'recover_banding';
  setShowMask(true);setBrush(v=>({...v,target:next}));if(state.phase==='ready'&&state.presented)void workflow.render({action:'replace',target:next,proposal:draftRef.current});
 };window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);},[state.open,state.phase,state.presented,workflow]);
 const locked=owner.pending||state.phase==='loading';
 function change(next:Proposal){dirtySerial.current++;setDraft(next);draftRef.current=next;workflow.dirty();}
 function update(target=brush.target){if(locked)return;sentSerial.current=dirtySerial.current;setBefore(false);setLoaded([]);void workflow.render({action:'replace',target,proposal:draftRef.current});}
 function target(next:Target){setBrush(v=>({...v,target:next}));if(state.phase==='ready'&&state.presented)update(next);}
 const sliders:[keyof Parameters,string,keyof typeof import('./model').CONTROL_IDS][]=[['intrusions','纯色背景祛穿帮','intrusions'],['blemish_background','背景祛瑕疵','background'],['blemish_floor','地面祛瑕疵','floor'],['uniformity','纯色背景光影均匀','uniformity'],['brightness','均匀后明度','brightness'],['banding','纯色背景祛色阶断层','banding'],['enhancement','背景增强（饱和度 / 对比）','enhancement']];
 return <section className="studioPanel" aria-label="影棚背景调整"><strong>影棚背景调整</strong><p><small>真实标记、局部修补、背景与地面分开处理。全部强度默认为零。</small></p>
  <button disabled={disabled||owner.pending||!owner.context.enabled||owner.context.canStart===false} onClick={()=>void workflow.start()}>编辑背景调整</button>
  {report?.suspended&&<p role="alert">已暂停：{report.suspended}</p>}{!state.open&&state.message&&<p role="status">{state.message}</p>}
  {!state.open&&state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原操作结果</button>}
  {state.open&&createPortal(<div className="studioWorkspace" role="dialog" aria-modal="true" aria-label="影棚纯色背景编辑"><header><strong>影棚背景调整</strong><span>原图标记与真实成片对照</span><button onClick={()=>workflow.cancel()}>取消 / Esc</button></header>
   <div className="studioTools"><label>背景来源<select disabled={locked} value={draft.region_mode} onChange={e=>change({...draft,region_mode:e.target.value as Proposal['region_mode']})}><option value="manual">显式手动标记</option value="semantic_background" disabled={!report?.semantic_available}>已验证人像模型背景（不含地面语义）</option></select></label>
    <label data-control-id={control(brush.target.startsWith('recover_')?'recovery':brush.target==='blemish'?'brush':'blemishes')}>编辑范围<select value={brush.target} disabled={locked} onChange={e=>target(e.target.value as Target)}>{(Object.keys(TARGETS) as Target[]).map(k=><option key={k} value={k}>{TARGETS[k]}</option>)}</select></label>
    <div role="group" aria-label="添加或减去">{(['add','subtract'] as const).map(k=><button key={k} data-control-id={control(k)} disabled={locked} aria-pressed={brush.operation===k} onClick={()=>setBrush(v=>({...v,operation:k}))}>{k==='add'?'添加':'减去'}</button>)}</div>
    {(['size','feather','flow','opacity'] as const).map((key,i)=><label key={key} data-control-id={control(key)}>{['大小','羽化','流量','不透明度'][i]}<input disabled={locked} type="range" min={key==='size'?1:0} max={key==='size'?60:100} value={brush[key]} onChange={e=>setBrush(v=>({...v,[key]:Number(e.target.value)}))}/><output>{brush[key]}%</output></label>)}
    <label data-control-id={control('source_mask')}><input type="checkbox" checked={showMask} onChange={e=>setShowMask(e.target.checked)}/>显示原图和蒙版</label>
    <button disabled={locked||!draft.strokes.some(s=>s.target===brush.target)} onClick={()=>change({...draft,strokes:draft.strokes.filter(s=>s.target!==brush.target)})}>清空当前目标笔迹</button>
   </div>
   <div className="studioAmounts" data-control-id={control('blemishes')}>{sliders.map(([key,label,id])=><label key={key} data-control-id={control(id)}>{label}<input type="range" min={key==='brightness'?-100:0} max={100} step={1} value={key==='brightness'?draft.parameters[key]:Math.round(draft.parameters[key]*100)} disabled={locked||(key==='brightness'&&draft.parameters.uniformity===0)} onChange={e=>change({...draft,parameters:{...draft.parameters,[key]:Number(e.target.value)/(key==='brightness'?1:100)}})}/><output>{key==='brightness'?draft.parameters[key]:Math.round(draft.parameters[key]*100)}</output></label>)}</div>
   {state.image&&<div className="studioPictures" style={{gridTemplateColumns:showMask?'1fr 1fr':'1fr'}}>{showMask&&<figure><figcaption>原图定位 · {TARGETS[brush.target]} · 松手后更新蒙版与照片</figcaption><StudioCanvas image={state.image} brush={brush} showMask={showMask} locked={locked||!state.presented} onStroke={s=>{change({...draftRef.current,strokes:[...draftRef.current.strokes,s]});update();}}/></figure>}
    <figure><figcaption><button aria-pressed={before} onClick={()=>setBefore(v=>!v)}>{before?'查看调整后':'查看本次调整前'}</button> 真实全效果输出（代理预览）</figcaption><img src={before?state.image.before:state.image.after} alt={before?'本次背景调整之前':'本次背景调整的实际输出'}/></figure>
    <div className="studioLoadProof" aria-hidden="true">{[state.image.before,state.image.after,state.image.source,state.image.mask].map((src,i)=><img key={`${state.previewId}-${i}`} src={src} alt="" onLoad={()=>setLoaded(v=>v.includes(src)?v:[...v,src])} onError={()=>workflow.failed('背景照片预览无法显示')}/>)}</div>
   </div>}
   <footer><p role="status">{state.message}</p>{state.image&&<p><small>{state.image.note}</small></p>}<p><small>前四项只处理可信纯色范围。地面必须手动标记；用保护笔保留人物、道具和接触阴影。恢复笔只撤回所选背景效果，不擦掉其他编辑。</small></p>
    <button data-control-id={control('update')} disabled={locked||!state.presented} onClick={()=>update()}>更新效果</button>
    <button data-control-id={control('confirm')} disabled={locked||!state.presented||!state.committable||sentSerial.current!==dirtySerial.current} onClick={()=>void workflow.confirm()}>确定</button>
    {state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原操作，不重复提交</button>}
    {state.phase==='failure'&&<button onClick={()=>{workflow.cancel();void workflow.start();}}>重新进入</button>}
    <details><summary>处理与导出说明</summary>{report?.boundaries.map(s=><p key={s}>{s}</p>)}</details>
   </footer>
  </div>,document.body)}
 </section>;
}
