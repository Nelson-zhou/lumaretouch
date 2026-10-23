import {useEffect,useState} from 'react';
import type {Guide} from './model';
import type {GuideOwner} from './useCanvasGuides';
import './guides.css';
export function GuideControls({owner:o}:{owner:GuideOwner}){
  const disabled=!o.canManage||o.pending;
  return <details className="guideControls"><summary>参考线 · {o.state.lines.length}</summary>
    <div className="guideMenu" role="group" aria-label="参考线控制">
      <p>{o.reason}</p>
      <button disabled={disabled} onClick={()=>o.add('horizontal')}>创建水平参考线 (R)</button>
      <button disabled={disabled} onClick={()=>o.add('vertical')}>创建垂直参考线 (Ctrl+R)</button>
      <button disabled={disabled} aria-pressed={o.state.visible} onClick={o.toggle}>{o.state.visible?'隐藏':'显示'}参考线 (Shift+R)</button>
      <button disabled={disabled||!o.state.lines.length} onClick={o.clear}>删除全部参考线</button>
      <button disabled={disabled||o.locked||!o.canUndo} onClick={o.undo}>撤销参考线操作</button>
      <button disabled={disabled||o.locked||!o.canRedo} onClick={o.redo}>重做参考线操作</button>
      {o.unresolved?<button disabled={o.working} onClick={o.query}>查询原操作</button>:<button disabled={o.working} onClick={o.read}>刷新参考线</button>}
      <div className="guideCoordinateList" aria-label="原图坐标列表">{o.state.lines.map((line,index)=><GuideCoordinate key={line.id} line={line} index={index} owner={o} disabled={disabled}/>)}</div>
      <p>拖动定位，方向键微调，Shift 加速，Delete 删除，Esc 取消拖动。独立视图撤销，不影响修图历史。</p>
      <p role="status" aria-live="polite">{o.message}</p>
    </div>
  </details>;
}

function GuideCoordinate({line,index,owner,disabled}:{line:Guide;index:number;owner:GuideOwner;disabled:boolean}){
  const [text,setText]=useState(String(Number((line.position*100).toFixed(4))));
  useEffect(()=>{setText(String(Number((line.position*100).toFixed(4))));},[line.position]);
  const commit=()=>{const value=Number(text);if(text.trim()!==''&&Number.isFinite(value)&&value>=0&&value<=100){
    if(Math.abs(value/100-line.position)>1e-8)owner.move(line.id,value/100);
  }else setText(String(line.position*100));};
  const label=`${line.axis==='vertical'?'垂直':'水平'} ${index+1}`;
  return <div><label>{label} · 原图 % <input aria-label={`${label}原图位置百分比`} type="number" min="0" max="100" step="0.1" value={text} disabled={disabled||owner.locked}
    onChange={e=>setText(e.target.value)} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();commit();}if(e.key==='Escape'){e.preventDefault();setText(String(line.position*100));}}}/></label>
    <button disabled={disabled} aria-label={`删除${label}参考线`} onClick={()=>owner.remove(line.id)}>删除</button></div>;
}
