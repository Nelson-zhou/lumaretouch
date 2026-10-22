import type {MaskObject} from './model';
export type RangePatch=Partial<{color:[number,number,number];tolerance:number;invert:boolean;low:number;high:number}>;
const hex=(color:[number,number,number])=>'#'+color.map(v=>Math.round(Math.max(0,Math.min(1,v))*255).toString(16).padStart(2,'0')).join('');
export function RangeControls({object,onChange}:{object:MaskObject;onChange:(patch:RangePatch)=>void}){
  if(object.kind==='color_range')return <>
    <label>目标颜色<input type="color" value={hex(object.color)} onChange={e=>{const s=e.target.value;onChange({color:[1,3,5].map(i=>parseInt(s.slice(i,i+2),16)/255) as [number,number,number]});}}/>{hex(object.color)}</label>
    <label>颜色容差<input type="range" min="0" max="100" value={object.tolerance*100} onChange={e=>onChange({tolerance:Number(e.target.value)/100})}/>{Math.round(object.tolerance*100)}%</label>
    <label><input type="checkbox" checked={object.invert===true} onChange={e=>onChange({invert:e.target.checked})}/>反转颜色选区（显示蒙版反相）</label>
    <small>反转的是此对象的实际选区，不是显示颜色。应用后影响调色与导出，可撤销；青色已保存范围不会随未应用草稿改变。</small>
  </>;
  if(object.kind==='luminance_range')return <>
    <label>最低线性亮度<input type="number" min="0" max={object.high*100} step="0.1" value={Number((object.low*100).toFixed(2))} onChange={e=>{const n=Number(e.target.value)/100;if(Number.isFinite(n))onChange({low:Math.max(0,Math.min(object.high,n))});}}/>%</label>
    <label>最高线性亮度<input type="number" min={object.low*100} max="100" step="0.1" value={Number((object.high*100).toFixed(2))} onChange={e=>{const n=Number(e.target.value)/100;if(Number.isFinite(n))onChange({high:Math.max(object.low,Math.min(1,n))});}}/>%</label>
  </>;
  return null;
}
