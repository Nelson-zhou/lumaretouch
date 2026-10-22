import {useLayoutEffect,useRef,useSyncExternalStore} from 'react';
import {KEYS,IDS,LABELS,HINTS,neutral,adjust,link,reason,type MouthShape,type MouthKey,type MouthSide,type MouthFact} from './model';
import {mouthInteraction as owner} from './interaction';
interface Props {
  value:MouthShape;facts?:Partial<Record<string,MouthFact>>;disabled:boolean;why?:string;
  documentId:string;faceId:string;revision:number;legacy:number;
}
export function MouthShapeControls({value,facts,disabled,why,documentId,faceId,revision,legacy}:Props) {
  const view=useSyncExternalStore(owner.subscribe,owner.snapshot,owner.snapshot);
  const gestures=useRef(new Map<string,string>());
  useLayoutEffect(()=>{owner.update({documentId,faceId,recipe:value,revision,enabled:!disabled});},[documentId,faceId,value,revision,disabled]);
  const gesture=(key:string)=>{let id=gestures.current.get(key);if(!id){id=crypto.randomUUID();gestures.current.set(key,id);}return id;};
  const end=(key:string)=>{gestures.current.delete(key);};
  const edit=(change:(r:MouthShape)=>MouthShape,key:MouthKey|'all',id=crypto.randomUUID())=>owner.edit(change,key,id);
  const blocked=disabled||view.phase==='uncertain'||!owner.ownsPending();
  const slider=(key:MouthKey,side?:MouthSide)=>{
    const id=side?`${key}:${side}`:key;
    const label=LABELS[key]+(side?` · 人物${side==='left'?'左':'右'}`:'');
    const n=key==='gummy'?view.recipe.gummy[side!]:view.recipe[key];
    const min=key==='gummy'?0:-100;
    const change=(v:number)=>{if(Number.isFinite(v))edit(r=>adjust(r,key,Math.min(100,Math.max(min,v))/100,side),key,gesture(id));};
    return <div className="pslider" key={id}>
      <label className="prow">{label}<input type="number" min={min} max={100} step={1} disabled={blocked} aria-label={`${label} 数值`} value={Math.round(n*100)} onChange={e=>change(e.currentTarget.valueAsNumber)} onFocus={()=>gesture(id)} onBlur={()=>end(id)}/></label>
      <input type="range" min={min} max={100} step={1} disabled={blocked} aria-label={label} value={Math.round(n*100)} title={HINTS[key]}
        onPointerDown={e=>{gesture(id);e.currentTarget.setPointerCapture(e.pointerId);}} onChange={e=>change(e.currentTarget.valueAsNumber)}
        onPointerUp={e=>{change(e.currentTarget.valueAsNumber);end(id);}} onPointerCancel={()=>end(id)} onKeyDown={()=>gesture(id)} onKeyUp={()=>end(id)} onBlur={()=>end(id)}/>
      <button type="button" disabled={blocked} onClick={()=>edit(r=>adjust(r,key,0,side),key)}>归零</button>
      {reason(facts?.[id])&&<p role="status" className="muted">{reason(facts?.[id])}</p>}
    </div>;
  };
  return <section data-control-id={IDS.family} aria-label="嘴部几何调整">
    <p className="muted">只搬运已有二维唇部纹理，不生成牙齿、牙龈或嘴部内部。唇妆独立保留。</p>
    {legacy!==0&&<p role="status" className="muted">旧版微笑仍为 {Math.round(legacy*100)}，原参数未被重置。M 唇会与它叠加，M 唇还调整唇峰与唇珠，不是微笑的别名。</p>}
    {KEYS.map(key=><div key={key} data-control-id={IDS[key]}>
      <p className="muted">{LABELS[key]}：{HINTS[key]}</p>
      {key==='gummy'?<>
        <button type="button" disabled={blocked} aria-pressed={view.recipe.gummy.linked} onClick={()=>edit(r=>link(r,!r.gummy.linked),key)}>{view.recipe.gummy.linked?'已联动，点击解锁':'已解锁，点击联动'}</button>
        {view.recipe.gummy.linked&&view.recipe.gummy.left!==view.recipe.gummy.right&&<p className="muted">左右原值保留，下一次调整才同步。左/右指人物自身。</p>}
        {slider(key,'left')}{slider(key,'right')}
      </>:slider(key)}
    </div>)}
    <button type="button" className="specBtn" disabled={blocked} onClick={()=>edit(()=>neutral(),'all')}>重置九项嘴形（不重置微笑或唇妆）</button>
    {view.phase==='working'&&<p role="status">正在应用预览，后续拖动已合并为最新意图。</p>}
    {view.message&&<p role="status">{view.message}</p>}
    {view.phase==='uncertain'&&<button type="button" onClick={()=>void owner.reconcile()}>查询本次结果（不重发修改）</button>}
    {why&&<p role="status" className="muted">{why}</p>}
    <p className="muted">露龈 0 至 100，其余 -100 至 100，幅度和可见性门槛均为本产品策略。仅露龈支持左右解锁；侧脸、遮挡、低对比可能保守拒绝，请检查预览。</p>
  </section>;
}
