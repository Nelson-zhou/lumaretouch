import type {ComponentType} from 'react';
import {CONTROL_IDS,LABELS,LINK_KEY,explanation,linkedPatch,linkPatch,type Region,type RegionFact} from './model';
type SliderProps={label:string;value:number;min:number;max:number;disabled?:boolean;title?:string;
  onChange:(value:number)=>void;onReset:()=>void};
export interface FacialWrinkleControlProps {
  region:Region;amounts:Record<string,number>;facts?:Record<string,RegionFact>;
  disabled:boolean;reason?:string;commit:(patch:Record<string,number>)=>void;Slider:ComponentType<SliderProps>;
}
/** Independent controls use the existing enhance receipt/history transaction.
 * Anatomical left/right mean the subject's sides, independent of preview mirroring.
 */
export function FacialWrinkleControl({region,amounts,facts,disabled,reason,commit,Slider}:FacialWrinkleControlProps) {
  const slider=(label:string,key:string,onChange?:(v:number)=>void,value=amounts[key]??0)=>{
    const why=reason??explanation(facts?.[key]);
    return <div key={key}>
      <Slider label={label} value={Math.round(value*100)} min={0} max={100} disabled={disabled}
        title={why??'只淡化选中部位线状细纹，保留五官、皮肤纹理与深层表情轮廓'}
        onChange={v=>onChange?onChange(v/100):commit({[key]:v/100})}
        onReset={()=>onChange?onChange(0):commit({[key]:0})}/>
      {why&&!reason&&<p className="muted" role="status">{why}</p>}
    </div>;
  };
  const left=amounts.wrinkle_nasolabial_left??0,right=amounts.wrinkle_nasolabial_right??0;
  const unlocked=amounts[LINK_KEY]===1;
  return <div data-control-id={`PC-32464-C-${CONTROL_IDS[region]}`}>
    {region!=='nasolabial'?slider(LABELS[region],`wrinkle_${region}`):<>
      <button type="button" className="specBtn" disabled={disabled} aria-pressed={unlocked}
        title="联动或解锁保留当前两侧数值；联动后的下一次拖动才同时调整两侧"
        onClick={()=>commit(linkPatch(!unlocked))}>{unlocked?'左右独立 · 点击联动':'左右联动 · 点击解锁'}</button>
      {unlocked?<>
        {slider('法令纹 · 人物左侧','wrinkle_nasolabial_left')}
        {slider('法令纹 · 人物右侧','wrinkle_nasolabial_right')}
      </>:<>
        {left!==right&&<p className="muted">两侧保留原值：左 {Math.round(left*100)} / 右 {Math.round(right*100)}。下次拖动将同时设置两侧。</p>}
        {slider('祛法令纹 · 左右联动','wrinkle_nasolabial_left',v=>commit(linkedPatch(v)),(left+right)/2)}
        {explanation(facts?.wrinkle_nasolabial_right)&&<p className="muted" role="status">人物右侧：{explanation(facts?.wrinkle_nasolabial_right)}</p>}
      </>}
    </>}
  </div>;
}
