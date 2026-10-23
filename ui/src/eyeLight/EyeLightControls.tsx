import {useState} from 'react';
import {ASSETS,degrees,neutral,neutralEye,patchEye,setLinked,REQUIREMENTS,type EyeLight,type EyeMaterial,type EyeSide,type EyeLightReceipt} from './model';
type Props={value:EyeLight;receipt:EyeLightReceipt;onChange:(value:EyeLight)=>void;onReview:()=>void};
export function EyeLightControls({value,receipt,onChange,onReview}:Props){
 const [side,setSide]=useState<EyeSide>('left'),eye=value[side];const disabled=receipt.status==='unavailable';
 const patch=(p:Partial<EyeMaterial>)=>onChange(patchEye(value,side,p));
 return <section aria-label="眼神光素材" data-requirement={REQUIREMENTS.family}>
  <h3>眼神光素材</h3><p>原创柔光箱与窗格叠加，与原有高光增强独立。不是恢复真实光源。</p>
  <p role="status">{receipt.reason??'双眼联动或左右独立；只作用已审核的可见眼球。'}</p>
  <button type="button" onClick={onReview} disabled={disabled}>审核当前人物可见眼球</button>
  <fieldset disabled={disabled}><legend>素材与位置</legend>
   <label>编辑眼侧<select value={side} onChange={e=>setSide(e.target.value as EyeSide)}><option value="left">人物左眼</option><option value="right">人物右眼</option></select></label>
   <label><input type="checkbox" checked={value.linked} onChange={e=>onChange(setLinked(value,e.target.checked,side))}/>联动双眼（开启时以当前眼参数为准）</label>
   <label>素材<select value={eye.asset} onChange={e=>patch({asset:e.target.value as EyeMaterial['asset']})}>{ASSETS.map((asset,i)=><option key={asset} value={asset}>{i===0?'原创柔光箱':'原创四格窗'}</option>)}</select></label>
   {(['strength','horizontal','vertical','rotation'] as const).map(key=><label key={key} data-requirement={REQUIREMENTS[key]}>
    {{strength:'程度',horizontal:'水平位置',vertical:'垂直位置',rotation:'旋转'}[key]}
    <input type="range" min={key==='strength'?0:-100} max={100} step={1} value={eye[key]} onChange={e=>patch({[key]:Number(e.target.value)})}/>
    <output>{eye[key]}{key==='rotation'?` (${degrees(eye.rotation)}°)`:''}</output>
   </label>)}
   <label data-requirement={REQUIREMENTS.flip}><input type="checkbox" checked={eye.flip} onChange={e=>patch({flip:e.target.checked})}/>水平翻转此眼素材</label>
   <button type="button" onClick={()=>patch(neutralEye())}>重置当前{value.linked?'双眼':'单眼'}</button>
   <button type="button" onClick={()=>onChange(neutral())}>重置全部眼神光</button>
  </fieldset><p>位置 ±100 对应一个观测虹膜半径，这是本地设计。闭眼、遮挡或分辨率不足时不应用。</p>
 </section>;
}
