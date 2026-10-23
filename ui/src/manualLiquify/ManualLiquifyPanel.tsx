import {GuideControls} from '../canvasGuides/GuideControls';
import type {GuideOwner} from '../canvasGuides/useCanvasGuides';
import type {DocState} from '../native';
import {useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {LABELS,type BrushSettings,type LiquifyMode,type LiquifyReport} from './model';
import type {ManualLiquifyOwner} from './useManualLiquifyWorkflow';
import {LiquifyCanvas} from './LiquifyCanvas';
import './manualLiquify.css';
export function ManualLiquifyPanel({owner,report,disabled=false,guides,guideSourceSize,guideCrop}:{guides?:GuideOwner;guideSourceSize?:[number,number];guideCrop?:DocState['crop'];owner:ManualLiquifyOwner;report?:LiquifyReport;disabled?:boolean}){
  const {state,workflow}=owner;
  const [settings,setSettings]=useState<BrushSettings>({mode:'push',size:10,density:50,pressure:50,rate:50,fixedEdges:true,direction:1,showMask:true});
  const [before,setBefore]=useState(false),[zoom,setZoom]=useState(100);
  const close=useRef<HTMLButtonElement|null>(null);
  useEffect(()=>{if(state.open)close.current?.focus();},[state.open]);
  useEffect(()=>{setBefore(false);},[state.previewId]);
  const locked=state.strokeActive||state.ending||owner.pending;
  const number=(key:'size'|'density'|'pressure'|'rate',value:number)=>setSettings(p=>({...p,[key]:value}));
  return <section className="manualLiquifyPanel" aria-label="手动液化">
    <strong>手动液化 · N</strong><p><small>在镜头/透视之前的真实效果上塑形，并查看最终光学效果；每笔可撤销。</small></p>
    <button disabled={disabled||owner.pending||!owner.context.enabled||owner.context.canStart===false} onClick={()=>void workflow.start()}>进入手动液化{report?.strokes.length?` · ${report.strokes.length} 笔`:''}</button>
    {report?.suspended&&<p role="alert">液化已暂停：{report.suspended}。不能忽略缺失笔迹后继续出片。</p>}
    {!state.open&&state.message&&<p role="status">{state.message}</p>}
    {state.phase==='uncertain'&&!state.open&&<button onClick={()=>void workflow.check()}>查询原笔迹结果</button>}
    {state.open&&createPortal(<div className="liquifyWorkspace" role="dialog" aria-modal="true" aria-label="手动液化工作区">
      <header><strong>手动液化</strong>{guides&&<GuideControls owner={guides}/>}<span>左侧可绘制，右侧最终效果只读 · 显示最终图后保存 · Esc 结束</span><button ref={close} onClick={()=>workflow.cancel()}>结束液化</button></header>
      <div className="liquifyModes" role="group" aria-label="液化工具">{(Object.keys(LABELS) as LiquifyMode[]).map(mode=><button key={mode} disabled={locked} aria-pressed={settings.mode===mode}
        onClick={()=>setSettings(p=>({...p,mode}))}>{LABELS[mode]}</button>)}</div>
      <div className="liquifyControls">
        {(['size','density','pressure','rate'] as const).map((key,i)=><label key={key}>{['大小','密度','压力','速率'][i]}
          <input type="range" min={key==='size'?.5:1} max={key==='size'?50:100} step={key==='size'?.5:1} value={settings[key]} disabled={locked} onChange={e=>number(key,Number(e.target.value))}/>
          <output>{settings[key]}{key==='size'?'% 短边':'%'}</output></label>)}
        <label><input type="checkbox" checked={settings.fixedEdges} disabled={locked} onChange={e=>setSettings(p=>({...p,fixedEdges:e.target.checked}))}/>固定边缘</label>
        <label><input type="checkbox" checked={settings.showMask} onChange={e=>setSettings(p=>({...p,showMask:e.target.checked}))}/>显示保护蒙版</label>
        {settings.mode==='rotate'&&<label>方向<select disabled={locked} value={settings.direction} onChange={e=>setSettings(p=>({...p,direction:Number(e.target.value) as 1|-1}))}><option value="1">顺时针</option><option value="-1">逆时针</option></select></label>}
      </div>
      <div className="liquifyViewControls"><button disabled={locked} aria-pressed={before} onClick={()=>setBefore(v=>!v)}>{before?'回到当前效果':'查看本笔之前'}</button>
        <label>画布缩放 <select disabled={locked} value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[50,75,100,150,200,300,400].map(v=><option key={v} value={v}>{v}%</option>)}</select></label>
        <small>{settings.mode==='reconstruct'?'重建只恢复手动形变，不撤回自动美型或调色':settings.mode==='freeze'||settings.mode==='thaw'?'红色代表当前位置的冻结保护；冻结不会倒退已有手动形变':settings.mode==='left'?'沿绘制时画面的水平方向向左推动':'密度控制作用范围，压力与速率控制力度；笔设备压力叠乘，按住可持续作用'}</small></div>
      <LiquifyCanvas guides={guides} guideSourceSize={guideSourceSize} guideCrop={guideCrop} owner={owner} settings={settings} showBefore={before} zoom={zoom}/>
      <footer><p role="status">{state.message}</p><small>矢量笔迹在全尺寸重新计算。两侧均为真实代理渲染；左侧不含镜头/透视，不代表全尺寸照片验收。</small>
        <div className="liquifyHistoryTools">{report?.strokes.length? <>
          <button disabled={locked||state.phase!=='drawing'} onClick={()=>workflow.mutate({action:'delete',id:report.strokes.at(-1)!.id})}>删除最后一笔</button>
          <button disabled={locked||state.phase!=='drawing'} onClick={()=>workflow.mutate({action:'clear'})}>重置全部手动液化与保护</button>
        </>:null}
        {state.phase==='uncertain'&&<button onClick={()=>void workflow.check()}>查询原笔迹，不重复提交</button>}
        {state.phase==='failure'&&<button onClick={()=>{workflow.cancel();void workflow.start();}}>重新进入</button>}</div>
        <details><summary>范围与顺序</summary>{report?.boundaries.map(line=><p key={line}><small>{line}</small></p>)}</details>
      </footer>
    </div>,document.body)}
  </section>;
}
