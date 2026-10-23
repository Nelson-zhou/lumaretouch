import type {ComponentType} from 'react';
import {scleraPurifyReadiness, SCLERA_PURIFY_CONTROL_ID, type ScleraPurifyCapability} from './model';

type SliderProps = {
  label:string;value:number;min:number;max:number;disabled?:boolean;title?:string;
  onChange:(value:number)=>void;onReset:()=>void;
};

/** Same canonical enhancement owner, with reset independent of native support. */
export function ScleraPurifyControl({amount,capability,disabled,faceOk,faceWhy,reason,resetDisabled,commit,Slider}: {
  amount:number;capability?:ScleraPurifyCapability | null;disabled:boolean;
  faceOk:boolean;faceWhy?:string;reason?:string | null;resetDisabled:boolean;
  commit:(patch:Record<string,number>)=>void;Slider:ComponentType<SliderProps>;
}) {
  const ready = scleraPurifyReadiness(capability);
  const why = !faceOk ? faceWhy : ready.reason ?? reason ?? undefined;
  return <div data-control-id={SCLERA_PURIFY_CONTROL_ID}>
    <p className="muted">仅减轻眼白局部暗淡瑕疵与偏色，不是整体提亮或祛红血丝。范围由眼部几何估计，并非语义分割；请对比调整前后，不能保证识别全部瑕疵。</p>
    <Slider label="眼白净化" value={Math.round(amount * 100)} min={0} max={100}
      disabled={disabled || !faceOk || !ready.available}
      title={why ?? '减轻眼白局部瑕疵与偏色；与眼白提亮、祛红血丝及祛红眼独立'}
      onChange={(v) => commit({sclera_purify: v / 100})}
      onReset={() => commit({sclera_purify: 0})} />
    {why && <p className="muted" role="status">{why}</p>}
    {amount > 0 && <button type="button" className="specBtn" disabled={resetDisabled}
      title="只归零当前编辑范围的眼白净化；保留眼白提亮、祛红血丝和其他参数，无需缺失的调整核心"
      onClick={() => commit({sclera_purify: 0})}>重置眼白净化</button>}
  </div>;
}
