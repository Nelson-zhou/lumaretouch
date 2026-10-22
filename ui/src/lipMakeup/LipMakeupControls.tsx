import type {ComponentType} from 'react';
import {KEYS,IDS,LABELS,neutral,patch,explanation,type LipMakeup,type LipFact,type LipKey} from './model';
type SliderProps={label:string;value:number;min:number;max:number;disabled?:boolean;title?:string;onChange:(v:number)=>void;onReset:()=>void};
export interface LipMakeupControlsProps {
  value:LipMakeup;fact?:LipFact;disabled:boolean;reason?:string;busy?:boolean;
  commit:(recipe:LipMakeup,control?:LipKey)=>void;Slider:ComponentType<SliderProps>;
}
/** Commit is one acknowledged recipe transaction, shared by history and preview.
 * Do not infer success from slider motion; surface the engine's eligibility error.
 */
export function LipMakeupControls({value,fact,disabled,reason,busy,commit,Slider}:LipMakeupControlsProps) {
  const why=reason??explanation(fact);
  return <section data-control-id={`PC-32471-C-${IDS.family}`} aria-label="唇妆增强">
    <p className="muted">只调整选中人物现有唇妆；不换口红，不改变嘴形。三个滑杆独立，0 为原样。</p>
    {KEYS.map(key=><div key={key} data-control-id={`PC-32471-C-${IDS[key]}`}>
      <Slider label={LABELS[key]} value={Math.round(value[key]*100)} min={-100} max={100} disabled={disabled||busy}
        title={key==='dimensionality'?'调节真实低中频唇部光影，保留细唇纹；不生成高光或锐化':`独立调整${LABELS[key]}；本产品定义 -100 至 100，非官网数值`}
        onChange={v=>commit(patch(value,key,v/100),key)} onReset={()=>commit(patch(value,key,0),key)}/>
    </div>)}
    <button type="button" className="specBtn" disabled={disabled||busy} onClick={()=>commit(neutral())}>重置三项唇妆调整</button>
    {why&&<p className="muted" role="status">{why}</p>}
    <p className="muted">仅支持可靠可见的嘴唇。遮挡检测并非完整分割；局部误选请用唇妆恢复画笔排除。</p>
  </section>;
}
