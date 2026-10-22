import {useEffect,useState} from 'react';
import {runFabric} from '../native';
export interface FabricState {amount:number;available:boolean;lit:boolean;scope:'all_clothes';reason:string|null}
export function FabricPanel({value,documentId,revision,disabled,onDone,note}:{value?:FabricState;documentId?:string;
  revision:number;disabled:boolean;onDone:()=>void;note:(message:string)=>void}){
  const [amount,setAmount]=useState(value?.amount??0),[busy,setBusy]=useState(false);
  useEffect(()=>{setAmount(value?.amount??0);},[value?.amount,documentId,revision]);
  const commit=async(next:number)=>{
    if(busy||!documentId)return;
    setBusy(true);
    try{await runFabric(next,documentId);onDone();}
    catch(error){setAmount(value?.amount??0);note(String(error));}
    finally{setBusy(false);}
  };
  const unavailable=disabled||busy||!documentId||!value?.available;
  return <section className="fabricPanel" aria-label="衣物细褶淡化">
    <div className="prow"><strong>衣物细褶淡化</strong><span>{Math.round(amount*100)}%</span></div>
    <input aria-label="衣物细褶淡化强度" type="range" min={0} max={100} step={1}
      value={Math.round(amount*100)} disabled={unavailable}
      onChange={event=>setAmount(Number(event.target.value)/100)}
      onPointerUp={event=>void commit(Number(event.currentTarget.value)/100)}
      onPointerCancel={()=>setAmount(value?.amount??0)}
      onKeyUp={event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(event.key))void commit(Number(event.currentTarget.value)/100);}}/>
    <button disabled={disabled||busy||!documentId||!(value?.amount)} onClick={()=>{setAmount(0);void commit(0);}}>归零</button>
    <p><small>仅淡化全图可信衣物区域的细小明暗褶痕，保留织纹、图案和衣服结构。不生成衣物，不承诺去除大褶皱。</small></p>
    {!value?.available&&<p role="status"><small>{value?.reason??'请先完成人像分析，获取衣物语义蒙版'}</small></p>}
    {!!value?.amount&&!value.lit&&<p role="status"><small>参数已保留，当前衣物图层未启用；请重新分析后再导出。</small></p>}
  </section>;
}
