import {useEffect,useRef} from 'react';
import type {LocalGradeLayer,LocalGradeReport} from './model';
import type {LiveGradeOwner} from './useLiveGradeWorkflow';
import type {GradeValues} from './liveGradeWorkflow';

const adjustKeys=new Set(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown']);
type InputOwner={index:number;pointer:number|null;keyboard:boolean};

export function LiveGradeControls({owner,layer,limits,disabled,documentId}:{
  owner:LiveGradeOwner;layer:LocalGradeLayer;limits:LocalGradeReport['grade_limits'];disabled:boolean;documentId:string;
}){
  const {workflow,state,busy}=owner;
  const control=useRef<InputOwner|null>(null);
  const ours=state.documentId===documentId&&state.groupId===layer.id;
  const values=ours&&state.values?state.values:layer.grade;
  const latest=useRef(values);latest.current=values;
  useEffect(()=>()=>{control.current=null;workflow.cancel('已关闭调色组面板，未提交调色已取消');},[workflow,documentId,layer.id]);
  useEffect(()=>{if(state.phase!=='editing')control.current=null;},[state.phase]);
  function begin(index:number,pointer:number|null,keyboard:boolean){
    if(disabled||!owner.enabled||busy||!workflow.begin(layer.id,layer.grade))return false;
    control.current={index,pointer,keyboard};return true;
  }
  function finish(){control.current=null;workflow.finish();}
  function cancel(){if(control.current){control.current=null;workflow.cancel();}}
  return <div className="liveGradeControls" aria-label="实时调节本组颜色" data-readonly-scopes>
    <small>拖动时直接预览主画布真实效果，松开保留为一次撤销。Esc、指针取消或窗口失焦会还原未提交调整。</small>
    {!layer.enabled&&<small>本组已关闭，调整不会影响照片；启用本组后才显示效果。</small>}
    {['色相','饱和','明度','混入比例'].map((label,index)=>{
      const limit=index===3?1:limits[index];
      return <label key={label}>{label}<input type="range" min={index===3?0:-limit} max={limit} step={.001}
        aria-label={`${layer.name} ${label}`} value={values[index]}
        disabled={disabled||!owner.enabled||(busy&&(!ours||state.phase!=='editing'||control.current?.index!==index))}
        onPointerDown={event=>{
          if(event.button!==0)return;
          event.currentTarget.focus();
          if(!begin(index,event.pointerId,false)){event.preventDefault();return;}
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerUp={event=>{
          if(control.current?.pointer!==event.pointerId)return;
          finish();
          if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={cancel} onLostPointerCapture={event=>{if(control.current?.pointer===event.pointerId)cancel();}}
        onKeyDown={event=>{
          if(!adjustKeys.has(event.key))return;
          if(control.current?.index===index&&control.current.keyboard)return;
          if(!begin(index,null,true))event.preventDefault();
        }}
        onKeyUp={event=>{if(adjustKeys.has(event.key)&&control.current?.index===index&&control.current.keyboard)finish();}}
        onBlur={cancel}
        onChange={event=>{
          const active=control.current;
          // Screen-reader/native accessibility changes may have neither a
          // pointer-down nor keyboard-down event. They are still real edits.
          if(!active&&!begin(index,null,false))return;
          if(control.current?.index!==index)return;
          const next=[...latest.current] as GradeValues;next[index]=Number(event.target.value);
          latest.current=next;workflow.change(next);
          if(!active)finish();
        }}/><output>{values[index].toFixed(3)}</output></label>;
    })}
    {ours&&state.message&&<p role="status">{state.message}</p>}
  </div>;
}

export function LiveGradeStatus({owner}:{owner:LiveGradeOwner}){
  if(!owner.state.message)return null;
  return <div role="status" className="sourcePatchStatus"><span>{owner.state.message}</span>
    {owner.state.phase==='uncertain'&&<><button onClick={()=>owner.workflow.check()}>查询原调色结果</button>
      <button onClick={()=>owner.workflow.acknowledgeReload()}>已重新打开照片</button></>}
    {owner.state.phase==='editing'&&<button onClick={()=>owner.workflow.cancel()}>取消本次调色</button>}
  </div>;
}
