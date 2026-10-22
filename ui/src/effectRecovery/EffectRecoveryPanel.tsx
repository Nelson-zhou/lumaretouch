import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {LABELS,type BrushSettings,type RecoveryReport} from './model';
import type {EffectRecoveryOwner} from './useEffectRecoveryWorkflow';
import {RecoverySource} from './RecoverySource';
import './effectRecovery.css';

function ResolveRecovery({owner}:{owner:EffectRecoveryOwner}){
  return <><button onClick={()=>void owner.workflow.check()}>查询原笔迹结果，不重复提交</button>
    <button disabled={!owner.context.enabled||owner.context.documentId===owner.state.request?.document_id}
      onClick={()=>owner.workflow.acknowledgeAfterReload()}>已重新打开照片</button></>;
}

function RenderedReview({owner}:{owner:EffectRecoveryOwner}){
  const {state,workflow}=owner,image=state.image;
  const [showBefore,setShowBefore]=useState(false),[loaded,setLoaded]=useState({before:'',after:''});
  useLayoutEffect(()=>{setShowBefore(false);},[state.previewId]);
  useLayoutEffect(()=>{
    if(showBefore||!image||!state.previewId||loaded.before!==image.before||loaded.after!==image.after)return;
    let live=true,second=0;const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{
      if(live)void workflow.imagePresented(state.previewId!);
    });});
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[image,state.previewId,loaded,workflow,showBefore]);
  if(!image)return <div className="recoveryResultWaiting">{state.phase==='failure'?'本笔未提交，请重新开始':'正在生成真实全效果图，显示后即可开始涂抹'}</div>;
  return <>
    <div className="recoveryCompareActions">
      <button className={!showBefore?'active':''} onClick={()=>setShowBefore(false)}>当前恢复效果</button>
      <button className={showBefore?'active':''} onClick={()=>setShowBefore(true)}>本笔之前</button>
    </div>
    <div className="recoveryActual" style={{aspectRatio:image.width/image.height}}>
      <img src={image.before} alt="本笔之前的真实全效果" className={showBefore?'':'concealed'}
        onLoad={()=>setLoaded(v=>({...v,before:image.before}))} onError={()=>workflow.failed('本笔之前的效果图无法显示')}/>
      <img src={image.after} alt="本笔恢复后的真实全效果" className={showBefore?'concealed':''}
        onLoad={()=>setLoaded(v=>({...v,after:image.after}))} onError={()=>workflow.failed('本笔恢复后的效果图无法显示')}/>
    </div>
    <small>真实全效果代理渲染。保留手工修补、形变和其他调色，不是原图混合。全尺寸质量需另行检查。</small>
  </>;
}

/** A continuous tool workspace, not an apply-confirmation dialog per stroke. */
export function EffectRecoveryPanel({owner,report,disabled=false}:{owner:EffectRecoveryOwner;report?:RecoveryReport;disabled?:boolean}){
  const {state,workflow}=owner;
  return <section className="effectRecoveryPanel" aria-label="功能专属恢复画笔">
    <strong>效果恢复画笔 · B</strong>
    <p><small>只擦回指定效果，其他编辑保留。每笔松手自动保存，可撤销。</small></p>
    <div className="recoveryLaunchers">{report?.targets.map(item=><button key={item.target}
      disabled={disabled||owner.pending||!owner.context.enabled||(!item.active&&!item.strokes.length)}
      title={item.reason??item.label} onClick={()=>{workflow.cancel();void workflow.start(item.target);}}>
      {item.label}{item.strokes.length?` · ${item.strokes.length} 笔`:''}</button>)}</div>
    {report?.suspended&&<p role="alert">恢复蒙版已暂停：{report.suspended}。对应效果被停用，未忽略笔迹。</p>}
    {!state.open&&state.message&&<p role="status">{state.message}</p>}
    <details><summary>支持范围</summary>{report?.boundaries.map(line=><p key={line}><small>{line}</small></p>)}</details>
  </section>;
}

/** Always mounted beside the main viewer; collapsing a tool never hides a pending workspace. */
export function EffectRecoveryWorkspace({owner,report}:{owner:EffectRecoveryOwner;report?:RecoveryReport}){
  const {state,workflow}=owner;
  const [settings,setSettings]=useState<BrushSettings>({size:6,strength:100,feather:2,operation:'add'});
  const focus=useRef<HTMLButtonElement|null>(null);
  useEffect(()=>{if(state.open)focus.current?.focus();},[state.open]);
  const target=report?.targets.find(item=>item.target===state.target);
  const controlsDisabled=state.strokeActive||state.ending||owner.pending;
  const number=(key:'size'|'strength'|'feather',value:number)=>setSettings(previous=>({...previous,[key]:value}));
  if(!state.open)return state.phase==='uncertain'?<div className="sourcePatchStatus" role="status">
    <span>{state.message}</span><ResolveRecovery owner={owner}/></div>:null;
  return createPortal(<div className="recoveryWorkspace" data-readonly-scopes role="dialog" aria-modal="true" aria-label="连续效果恢复画笔">
      <header><strong>{LABELS[state.target]} · 专属恢复画笔</strong>
        <span>松手自动提交一笔 · Esc 结束</span><button ref={focus} onClick={()=>workflow.cancel()}>结束画笔</button></header>
      <div className="recoveryBrushControls">
        <label>画笔大小 <input type="range" min=".5" max="25" step=".5" value={settings.size} disabled={controlsDisabled}
          onChange={e=>number('size',Number(e.target.value))}/><output>{settings.size}% 画布短边</output></label>
        <label>强度 <input type="range" min="1" max="100" step="1" value={settings.strength} disabled={controlsDisabled}
          onChange={e=>number('strength',Number(e.target.value))}/><output>{settings.strength}%</output></label>
        <label>羽化 <input type="range" min="0" max="100" step="1" value={settings.feather} disabled={controlsDisabled}
          onChange={e=>number('feather',Number(e.target.value))}/><output>{settings.feather}</output></label>
        <label>方式 <select value={settings.operation} disabled={controlsDisabled}
          onChange={e=>setSettings(p=>({...p,operation:e.target.value as 'add'|'subtract'}))}>
          <option value="add">局部擦回该效果之前</option><option value="subtract">减少恢复，重新显示效果</option></select></label>
      </div>
      <div className="recoveryPanes"><section><h3>源图定位</h3><RecoverySource owner={owner} settings={settings}/>
        <small>原始源图坐标，保留构图。此处线条仅表示笔迹位置，不是处理效果。形变后的实际效果见右侧。</small></section>
        <section><h3>实际全效果</h3><RenderedReview owner={owner}/></section></div>
      <footer><p role="status">{state.message}</p>
        <small>羽化采用原图短边 0–5% 的空间过渡；添加笔迹取最大覆盖，不以重复描画叠加强度。</small>
        {target?.strokes.length? <div className="recoveryHistoryTools">
          <button disabled={controlsDisabled||state.phase!=='drawing'} onClick={()=>workflow.mutate({action:'enable',target:state.target,enabled:!target.enabled})}>{target.enabled?'暂时停用此目标恢复':'启用此目标恢复'}</button>
          <button disabled={controlsDisabled||state.phase!=='drawing'} onClick={()=>workflow.mutate({action:'delete',target:state.target,id:target.strokes.at(-1)!.id})}>删除此目标最后一笔</button>
          <button disabled={controlsDisabled||state.phase!=='drawing'} onClick={()=>workflow.mutate({action:'clear',target:state.target})}>清除此目标恢复</button>
        </div>:null}
        {state.phase==='uncertain'&&<ResolveRecovery owner={owner}/>}
        {state.phase==='failure'&&<button onClick={()=>{workflow.cancel();void workflow.start(state.target);}}>重新开始</button>}
      </footer>
    </div>,document.body);
}
