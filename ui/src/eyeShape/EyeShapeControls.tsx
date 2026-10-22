import type {PeopleContext} from '../people/model';
import {useLayoutEffect,useRef,useSyncExternalStore} from 'react';
import {KEYS,IDS,LABELS,HINTS,neutral,adjust,link,reason,type EyeShape,type EyeKey,type EyeFact} from './model';
import {eyeInteraction as owner} from './interaction';
export function EyeShapeControls({value,facts,disabled,why,documentId,faceId,revision,legacy,clearLegacy,peopleContext}:{value:EyeShape;facts?:Partial<Record<string,EyeFact>>;legacy:number;clearLegacy:()=>void;disabled:boolean;why?:string;documentId:string;faceId:string;revision:number;peopleContext?:PeopleContext}) {
  const view=useSyncExternalStore(owner.subscribe,owner.snapshot,owner.snapshot);
  const gestures=useRef(new Map<string,string>());
  useLayoutEffect(()=>{owner.update({documentId,faceId,recipe:value,revision,enabled:!disabled,peopleContext});},[documentId,faceId,value,revision,disabled,peopleContext]);
  const gesture=(key:string)=>{let id=gestures.current.get(key);if(!id){id=crypto.randomUUID();gestures.current.set(key,id);}return id;};
  const end=(key:string)=>{gestures.current.delete(key);};
  const edit=(change:(r:EyeShape)=>EyeShape,k:EyeKey|'all',id:string=crypto.randomUUID())=>owner.edit(change,k,id);
  const blocked=disabled||view.phase==='uncertain'||!owner.ownsPending();
  return <section data-control-id={IDS.family} aria-label="眼部几何调整">
    <p className="muted">左/右均指人物自身。只搬运已有二维纹理，不生成眼白、虹膜或睫毛；闭眼不能变成真实睁眼。</p>
    {legacy!==0&&<div role="status" className="muted">
      <p>旧版大眼仍为 {Math.round(legacy*100)}，原效果未被转换或重置。新版整体大小不能与它叠加，其他九项可独立调整。</p>
      <button type="button" disabled={blocked||owner.busy()} onClick={clearLegacy}>将旧版大眼归零（外观会改变，可撤销）</button>
      <p>这不是无损迁移。请比较归零前后，再决定是否使用新版整体大小。</p>
    </div>}
    {KEYS.map(k=><div key={k} data-control-id={IDS[k]}>
      <button type="button" className="specBtn" disabled={blocked} aria-pressed={view.recipe[k].linked} onClick={()=>edit(r=>link(r,k,!r[k].linked),k)}>{LABELS[k]}：{view.recipe[k].linked?'已联动，点击解锁':'已解锁，点击联动'}</button>
      {view.recipe[k].linked&&view.recipe[k].left!==view.recipe[k].right&&<p className="muted">两侧原值已保留；下一次调整任意一侧才会同步。</p>}
      {(['left','right'] as const).map(side=>{const key=`${k}:${side}`,label=`${LABELS[k]} · 人物${side==='left'?'左':'右'}`;
        const change=(n:number)=>{if(Number.isFinite(n))edit(r=>adjust(r,k,side,Math.min(100,Math.max(-100,n))/100),k,gesture(key));};
        return <div className="pslider" key={side}><label className="prow">{label}<input type="number" min={-100} max={100} step={1} aria-label={`${label} 数值`} disabled={blocked||(k==='size'&&legacy!==0)} value={Math.round(view.recipe[k][side]*100)} onChange={e=>change(e.currentTarget.valueAsNumber)} onFocus={()=>gesture(key)} onBlur={()=>end(key)}/></label>
          <input type="range" min={-100} max={100} step={1} disabled={blocked||(k==='size'&&legacy!==0)} aria-label={label} value={Math.round(view.recipe[k][side]*100)} title={`${HINTS[k]}；本产品 -100 至 100，非官网数值。`}
            onPointerDown={e=>{gesture(key);e.currentTarget.setPointerCapture(e.pointerId);}} onChange={e=>change(e.currentTarget.valueAsNumber)}
            onPointerUp={e=>{change(e.currentTarget.valueAsNumber);end(key);}} onPointerCancel={()=>end(key)}
            onKeyDown={()=>gesture(key)} onKeyUp={()=>end(key)} onBlur={()=>end(key)}/>
          <button type="button" disabled={blocked} onClick={()=>edit(r=>adjust(r,k,side,0),k)}>归零</button>
          {reason(facts?.[`${side}:${k}`])&&<p role="status" className="muted">{reason(facts?.[`${side}:${k}`])}</p>}
        </div>;})}
    </div>)}
    <button type="button" className="specBtn" disabled={blocked} onClick={()=>edit(()=>neutral(),'all')}>重置十项眼形调整</button>
    {view.phase==='working'&&<p role="status">正在应用预览；后续拖动已合并为最新意图。</p>}
    {view.message&&<p role="status">{view.message}</p>}
    {view.phase==='uncertain'&&<button type="button" onClick={()=>void owner.reconcile()}>查询本次结果（不重发修改）</button>}
    {why&&<p role="status" className="muted">{why}</p>}
    <p className="muted">数值 -100 至 100、几何幅度和可见性门槛为本产品策略，不是官网规定。遮挡检测不是完整眼镜/眼部分割；侧脸、反光、低对比可能保守拒绝，请检查预览。</p>
  </section>;
}
