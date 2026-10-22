import type {ColorActionOwner} from './useColorActionPicker';
import {COLOR_ACTION_NAMES,COLOR_CHANNEL_NAMES,colorActionLimit,type ColorAction,type ColorChannel} from './model';
import './colorActions.css';

export interface ColorActionControlsProps {owner:ColorActionOwner;onStart:(action:ColorAction,channel?:ColorChannel)=>void;blocked?:boolean}
export function ColorActionLaunch({owner,onStart,blocked=false,action,channel='master'}:ColorActionControlsProps&{action:ColorAction;channel?:ColorChannel}){
  const selected=owner.active&&owner.state.action===action&&owner.state.channel===channel;
  const control=action==='levels_black'?'PC-32455-C-58fb48cdf9':action==='levels_white'?'PC-32455-C-73ee12d5c4':action==='curve'?'PC-32455-C-d30dc5a133':'PC-32455-C-3791959b40';
  return <button type="button" data-spec-control={control} aria-pressed={selected}
    disabled={blocked||owner.pending||!owner.context.enabled||owner.context.canStart===false}
    title={action==='curve'?`${COLOR_CHANNEL_NAMES[channel]}：在照片上选点并上下拖动`:action==='hsl'?'在照片上选色并左右拖动，调整八色权重色相':'在冻结的色阶前输入上取样，自动提交一次'}
    onClick={()=>selected?owner.workflow.cancel():onStart(action,channel)}>{selected?'退出':action==='curve'?`${COLOR_CHANNEL_NAMES[channel]} `:''}{COLOR_ACTION_NAMES[action]}</button>;
}
export function ColorActionReadout({owner}:{owner:ColorActionOwner}){
  const {state,workflow}=owner,{sample,action,preview}=state;
  if(!action||(!owner.active&&!owner.pending))return null;
  const adjustable=action==='curve'||action==='hsl';
  return <section className="colorActionReadout" data-readonly-scopes aria-label="定向取样与工具阶段预览">
    <strong>{COLOR_ACTION_NAMES[action]}{action==='curve'&&state.channel?` · ${COLOR_CHANNEL_NAMES[state.channel]}`:''}</strong>
    {sample&&<>
      <div>RGB（sRGB）：{sample.mean_srgb.map(v=>v.toFixed(4)).join(' / ')}</div>
      <div>HSL：{sample.hsl[0].toFixed(1)}° / {(sample.hsl[1]*100).toFixed(1)}% / {(sample.hsl[2]*100).toFixed(1)}% · {sample.samples} 像素</div>
      {sample.point&&<div>曲线节点：输入 {sample.point[0].toFixed(4)}，输出 {sample.point[1].toFixed(4)}</div>}
      {sample.weights&&<small>八段权重：{sample.weights.map(v=>`${Math.round(v*100)}%`).join(' / ')}</small>}
      {typeof sample.achieved_delta==='number'&&<small>实际调整：{sample.achieved_delta.toFixed(action==='hsl'?2:4)}{action==='hsl'?'°':''}</small>}
    </>}
    {action==='hsl'&&<small>读数为真实 HSL；现有八色渲染仍采用 HSV 算子，此处仅定向调整色相。</small>}
    {preview&&<figure><img src={`data:image/png;base64,${preview.data}`} width={preview.width} height={preview.height}
      alt="引擎真实计算的当前工具阶段预览，不是完整处理链最终效果"/>
      <figcaption>工具阶段预览 · 非最终处理链{state.phase==='probing'?' · 正在更新':''}</figcaption></figure>}
    {adjustable&&<label className="colorActionDelta">{action==='hsl'?'色相偏移（度）':'曲线输出偏移'}
      <input type="range" min={-colorActionLimit(action)} max={colorActionLimit(action)} step={action==='hsl'?.1:.001}
        value={state.delta} disabled={!state.region||owner.pending||!owner.active}
        aria-label={action==='hsl'?'定向色相偏移':'定向曲线输出偏移'}
        onPointerDown={event=>event.currentTarget.setPointerCapture(event.pointerId)}
        onChange={event=>workflow.adjust(event.target.valueAsNumber)}
        onPointerUp={()=>workflow.finish()} onPointerCancel={()=>workflow.cancel()}
        onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();workflow.cancel();}}}
        onKeyUp={event=>{if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(event.key))workflow.finish();}}
        onBlur={()=>workflow.finish()}/>
      <output>{state.delta.toFixed(action==='hsl'?1:3)}{action==='hsl'?'°':''}</output>
    </label>}
    <small>{adjustable?'点击只选择并预览，不写入历史。画面拖动、滑杆或方向键松开后自动提交一次。':'取样 5×5 邻域，边缘裁切；验证后自动应用一次。'}</small>
    <div role="status">{state.message}</div>
    <button type="button" disabled={owner.pending} onClick={()=>workflow.cancel()}>取消，保留原图</button>
  </section>;
}
export function ColorActionStatus({owner}:{owner:ColorActionOwner}){
  const {state,workflow,context}=owner;
  if(!state.message||!['sending','waiting','uncertain','success','failure'].includes(state.phase))return null;
  return <div className="sourcePatchStatus" role="status"><span>{state.message}</span>
    {state.phase==='uncertain'&&<><button type="button" onClick={()=>void workflow.check()}>查询原定向调整结果</button>
      <button type="button" disabled={!context.enabled||context.documentId===state.request?.document_id} onClick={()=>workflow.acknowledgeAfterReload()}>已重新打开照片</button></>}
  </div>;
}
