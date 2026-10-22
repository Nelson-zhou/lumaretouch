import type {PeopleContext} from '../people/model';
import {useLayoutEffect,useRef,useSyncExternalStore} from 'react';
import {KEYS,IDS,LABELS,HINTS,neutral,adjust,link,reason,type BrowShape,type BrowKey,type BrowFact} from './model';
import {browInteraction as owner} from './interaction';
export function BrowShapeControls({value,facts,disabled,why,documentId,faceId,revision,peopleContext}:{value:BrowShape;facts?:Partial<Record<'left'|'right',BrowFact>>;disabled:boolean;why?:string;documentId:string;faceId:string;revision:number;peopleContext?:PeopleContext}) {
  const view=useSyncExternalStore(owner.subscribe,owner.snapshot,owner.snapshot);
  const gestures=useRef(new Map<string,string>());
  useLayoutEffect(()=>{owner.update({documentId,faceId,recipe:value,revision,enabled:!disabled,peopleContext});},[documentId,faceId,value,revision,disabled,peopleContext]);
  const gesture=(key:string)=>{let id=gestures.current.get(key);if(!id){id=crypto.randomUUID();gestures.current.set(key,id);}return id;};
  const end=(key:string)=>{gestures.current.delete(key);};
  const edit=(change:(r:BrowShape)=>BrowShape,k:BrowKey|'all',id=crypto.randomUUID())=>owner.edit(change,k,id);
  const blocked=disabled||view.phase==='uncertain'||!owner.ownsPending();
  return <section data-control-id={IDS.family} aria-label="眉毛几何调整">
    <p className="muted">左/右均指人物自身。只调整现有眉毛形状，不生发、不补眉、不更换素材。</p>
    {KEYS.map(k=><div key={k} data-control-id={IDS[k]}>
      <button type="button" className="specBtn" disabled={blocked} aria-pressed={view.recipe[k].linked} onClick={()=>edit(r=>link(r,k,!r[k].linked),k)}>{LABELS[k]}：{view.recipe[k].linked?'已联动，点击解锁':'已解锁，点击联动'}</button>
      {view.recipe[k].linked&&view.recipe[k].left!==view.recipe[k].right&&<p className="muted">两侧原值已保留；下一次调整任意一侧才会同步。</p>}
      {(['left','right'] as const).map(side=>{const key=`${k}:${side}`,label=`${LABELS[k]} · 人物${side==='left'?'左':'右'}`;
        const change=(n:number)=>{if(Number.isFinite(n))edit(r=>adjust(r,k,side,Math.min(100,Math.max(-100,n))/100),k,gesture(key));};
        return <div className="pslider" key={side}><label className="prow">{label}<input type="number" min={-100} max={100} step={1} aria-label={`${label} 数值`} disabled={blocked} value={Math.round(view.recipe[k][side]*100)} onChange={e=>change(e.currentTarget.valueAsNumber)} onFocus={()=>gesture(key)} onBlur={()=>end(key)}/></label>
          <input type="range" min={-100} max={100} step={1} disabled={blocked} aria-label={label} value={Math.round(view.recipe[k][side]*100)} title={`${HINTS[k]}；本产品 -100 至 100，非官网数值。`}
            onPointerDown={e=>{gesture(key);e.currentTarget.setPointerCapture(e.pointerId);}} onChange={e=>change(e.currentTarget.valueAsNumber)}
            onPointerUp={e=>{change(e.currentTarget.valueAsNumber);end(key);}} onPointerCancel={()=>end(key)}
            onKeyDown={()=>gesture(key)} onKeyUp={()=>end(key)} onBlur={()=>end(key)}/>
          <button type="button" disabled={blocked} onClick={()=>edit(r=>adjust(r,k,side,0),k)}>归零</button>
        </div>;})}
    </div>)}
    <button type="button" className="specBtn" disabled={blocked} onClick={()=>edit(()=>neutral(),'all')}>重置七项眉形调整</button>
    {view.phase==='working'&&<p role="status">正在应用预览；后续拖动已合并为最新意图。</p>}
    {view.message&&<p role="status">{view.message}</p>}
    {view.phase==='uncertain'&&<button type="button" onClick={()=>void owner.reconcile()}>查询本次结果（不重发修改）</button>}
    {why&&<p role="status" className="muted">{why}</p>}
    {(['left','right'] as const).map(side=>reason(facts?.[side])&&<p key={side} role="status" className="muted">人物{side==='left'?'左':'右'}眉：{reason(facts?.[side])}</p>)}
    <p className="muted">遮挡检测并非完整眉毛分割。浅眉、侧脸或遮挡时保守拒绝；请检查实际预览。</p>
  </section>;
}
