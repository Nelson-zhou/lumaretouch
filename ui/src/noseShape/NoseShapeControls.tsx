import {useEffect,useRef,useSyncExternalStore} from 'react';
import {KEYS,IDS,LABELS,HINTS,neutral,adjust,reason,type NoseShape,type NoseKey,type NoseFact} from './model';
import {noseInteraction as owner} from './interaction';
export function NoseShapeControls({value,facts,disabled,why,documentId,faceId,revision}:{value:NoseShape;facts?:Partial<Record<NoseKey,NoseFact>>;disabled:boolean;why?:string;documentId:string;faceId:string;revision:number}){
  const view=useSyncExternalStore(owner.subscribe,owner.snapshot,owner.snapshot);
  const gestures=useRef(new Map<NoseKey,string>());
  useEffect(()=>{owner.update({documentId,faceId,recipe:value,revision,enabled:!disabled});},[documentId,faceId,value,revision,disabled]);
  const gesture=(key:NoseKey)=>{let id=gestures.current.get(key);if(!id){id=crypto.randomUUID();gestures.current.set(key,id);}return id;};
  const end=(key:NoseKey)=>{gestures.current.delete(key);};
  const edit=(change:(r:NoseShape)=>NoseShape,k:NoseKey|'all',id=crypto.randomUUID())=>owner.edit(change,k,id);
  const blocked=disabled||view.phase==='uncertain'||!owner.ownsPending();
  return <section data-control-id={IDS.family} aria-label="鼻子二维几何调整">
    <p className="muted">只调整已有鼻部纹理，不生成缺失部位、不做三维重建。鼻高是上下位置；左右是位置，不是左右侧独立开关。</p>
    {KEYS.map(k=>{
      const change=(n:number)=>{if(Number.isFinite(n))edit(r=>adjust(r,k,Math.min(100,Math.max(-100,n))/100),k,gesture(k));};
      return <div key={k} data-control-id={IDS[k]}>
        <div className="pslider"><label className="prow">{LABELS[k]}<input type="number" min={-100} max={100} step={1} aria-label={`${LABELS[k]} 数值`} disabled={blocked} value={Math.round(view.recipe[k]*100)} onChange={e=>change(e.currentTarget.valueAsNumber)} onFocus={()=>gesture(k)} onBlur={()=>end(k)}/></label>
          <input type="range" min={-100} max={100} step={1} disabled={blocked} aria-label={LABELS[k]} value={Math.round(view.recipe[k]*100)} title={`${HINTS[k]}；本产品 -100 至 100，默认 0，非官网数值。`}
            onPointerDown={e=>{gesture(k);e.currentTarget.setPointerCapture(e.pointerId);}} onChange={e=>change(e.currentTarget.valueAsNumber)}
            onPointerUp={e=>{change(e.currentTarget.valueAsNumber);end(k);}} onPointerCancel={()=>end(k)} onKeyDown={()=>gesture(k)} onKeyUp={()=>end(k)} onBlur={()=>end(k)}/>
          <button type="button" disabled={blocked} onClick={()=>edit(r=>adjust(r,k,0),k)}>归零</button>
        </div>
        {reason(facts?.[k])&&<p role="status" className="muted">{LABELS[k]}：{reason(facts?.[k])}</p>}
      </div>;
    })}
    <button type="button" className="specBtn" disabled={blocked} onClick={()=>edit(()=>neutral(),'all')}>重置六项鼻形调整</button>
    {view.phase==='working'&&<p role="status">正在应用预览；后续拖动已合并为最新意图。</p>}
    {view.message&&<p role="status">{view.message}</p>}
    {view.phase==='uncertain'&&<button type="button" onClick={()=>void owner.reconcile()}>查询本次结果（不重发修改）</button>}
    {why&&<p role="status" className="muted">{why}</p>}
    <p className="muted">侧脸、遮挡和低对比时保守拒绝。检测不是完整鼻部/遮挡分割，请检查实际预览。</p>
  </section>;
}
