import {useEffect,useRef,useState} from 'react';
import {registerCurveEditBarrier} from '../curveEditBarrier';
import {ParametricGesture} from '../parametricGesture';
import {neutralParametric,parametricCurveSpec} from '../curveModel';
import {dragParametricCurve,type CurveSpec,type CurvePreview,type ParametricSpec} from '../native';
const keys=['shadows','darks','lights','highlights'] as const;
const names=['阴影','暗调','亮调','高光'];
const clamp=(n:number,lo:number,hi:number)=>Math.max(lo,Math.min(hi,n));
type Pointer={id:number;kind:'tone'|'split';index:number};
type Props={value:CurveSpec;samples:CurvePreview|null;disabled:boolean;resetToken:number;
  submit:(value:CurveSpec,id?:string,interactive?:boolean)=>void|Promise<void>;onBusy:(busy:boolean)=>void;note:(text:string)=>void};
export function ParametricCurveEditor(props:Props){
  const latest=useRef(props);latest.current=props;
  const [busy,setBusy]=useState(false);const pointer=useRef<Pointer|null>(null);
  const control=useRef<string|null>(null);const owner=useRef<EventTarget|null>(null);const rangePointer=useRef<number|null>(null);
  const [gesture]=useState(()=>new ParametricGesture({
    send:(spec,id,interactive)=>latest.current.submit(spec,id,interactive),
    busy:active=>{setBusy(active);latest.current.onBusy(active);if(!active){pointer.current=null;control.current=null;owner.current=null;rangePointer.current=null;}},
    error:text=>latest.current.note(text),
  },(value,region,target)=>dragParametricCurve(parametricCurveSpec(value),region,target)));
  useEffect(()=>{const remove=registerCurveEditBarrier(()=>gesture.settle(),()=>gesture.busy);return ()=>{remove();gesture.abort();};},[gesture]);
  useEffect(()=>{gesture.abort();pointer.current=null;control.current=null;owner.current=null;rangePointer.current=null;},[props.resetToken,gesture]);
  const spec=parametricCurveSpec(props.value),p=spec.parametric;
  const unavailable=props.disabled||!spec.enabled;
  const inactive=unavailable||!p.enabled;
  const start=(key:string)=>{
    if(inactive||gesture.closing)return false;
    if(gesture.busy)return control.current===key;
    control.current=key;return gesture.begin(latest.current.value);
  };
  const change=(patch:Partial<ParametricSpec>,key?:string)=>{
    const next=parametricCurveSpec(latest.current.value);Object.assign(next.parametric,patch);
    if(gesture.busy){if(control.current===key)gesture.apply(next);}
    else latest.current.submit(next);
  };
  const split=(index:number,value:number,key?:string)=>{
    const next=parametricCurveSpec(latest.current.value),bounds=[0,...next.parametric.splits,1];
    next.parametric.splits[index]=clamp(value,bounds[index]+.01,bounds[index+2]-.01);
    if(gesture.busy){if(control.current===key)gesture.apply(next);}else latest.current.submit(next);
  };
  const finish=(cancel=false)=>{void gesture.finish(cancel);};
  const keyboard=(e:React.KeyboardEvent,key:string)=>{
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'].includes(e.key))start(key);
    if(e.key==='Escape'&&gesture.busy){e.preventDefault();e.stopPropagation();finish(true);}
  };
  const rangeEvents=(key:string)=>({
    onPointerDown:(e:React.PointerEvent<HTMLInputElement>)=>{
      if(e.button!==0)return;e.currentTarget.focus();
      if(gesture.busy||!start(key))return;
      owner.current=e.currentTarget;rangePointer.current=e.pointerId;e.currentTarget.setPointerCapture(e.pointerId);
    },
    onPointerUp:(e:React.PointerEvent<HTMLInputElement>)=>{if(owner.current===e.currentTarget&&rangePointer.current===e.pointerId)finish();},
    onPointerCancel:(e:React.PointerEvent<HTMLInputElement>)=>{if(owner.current===e.currentTarget&&rangePointer.current===e.pointerId)finish(true);},
    onLostPointerCapture:(e:React.PointerEvent<HTMLInputElement>)=>{if(owner.current===e.currentTarget&&rangePointer.current===e.pointerId)finish();},
    onBlur:(e:React.FocusEvent<HTMLInputElement>)=>{if(owner.current===e.currentTarget)finish();},
    onKeyDown:(e:React.KeyboardEvent<HTMLInputElement>)=>{keyboard(e,key);if(control.current===key)owner.current=e.currentTarget;},
    onKeyUp:(e:React.KeyboardEvent<HTMLInputElement>)=>{if(owner.current===e.currentTarget&&e.key!=='Escape')finish();},
  });
  const bounds=[0,...p.splits,1];
  return <section aria-label="参数曲线" onKeyDownCapture={e=>{
    if(gesture.busy&&(e.key==='Escape'||((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'&&!e.shiftKey))){
      e.preventDefault();e.stopPropagation();finish(true);
    }
  }}>
    <div style={{display:'flex',gap:8,alignItems:'center'}}>
      <label><input type="checkbox" checked={p.enabled} disabled={unavailable||busy}
        onChange={e=>change({enabled:e.target.checked})}/>参数阶段</label>
      <button type="button" disabled={unavailable||busy} onClick={()=>change(neutralParametric())}>重置参数阶段</button>
    </div>
    <svg viewBox="0 0 256 280" tabIndex={inactive?-1:0} onBlur={e=>{if(owner.current===e.currentTarget)finish();}} role="img" aria-label="参数曲线：圆点调整明暗，底部三角点调整分区"
      style={{width:'100%',display:'block',background:'#202025',touchAction:'none',opacity:inactive?.45:1}}
      onPointerMove={e=>{
        const a=pointer.current;if(!a||a.id!==e.pointerId||inactive||gesture.closing)return;
        const r=e.currentTarget.getBoundingClientRect();if(r.width<=0||r.height<=0)return;const x=clamp((e.clientX-r.left)/r.width,0,1);
        const y=clamp(1-(e.clientY-r.top)/r.height*280/256,0,1);
        if(a.kind==='tone')gesture.solve(a.index,y);else split(a.index,x,`split-${a.index}`);
      }}
      onPointerUp={e=>{if(pointer.current?.id===e.pointerId)finish();}}
      onPointerCancel={e=>{if(pointer.current?.id===e.pointerId)finish(true);}} onLostPointerCapture={e=>{if(pointer.current?.id===e.pointerId)finish();}}>
      {[64,128,192].map(n=><path key={n} d={`M${n} 0V256 M0 ${n}H256`} stroke="#3a3a42"/>)}
      <path d="M0 256L256 0" stroke="#62626a" strokeDasharray="3 4" fill="none"/>
      {props.samples?.parametric&&<polyline points={props.samples.parametric.map((y,x)=>`${x},${256-y*256}`).join(' ')} fill="none" stroke="#e8c779" strokeWidth="2"/>}
      {p.splits.map((x,i)=><g key={i}>
        <path d={`M${x*256} 0V256`} stroke="#666671" strokeDasharray="2 4"/>
        <path d={`M${x*256} 256l-7 13h14z`} fill="#b6b6c4" style={{cursor:inactive?'default':'ew-resize'}}
          onPointerDown={e=>{
            if(e.button!==0)return;const svg=e.currentTarget.ownerSVGElement;svg?.focus();
            if(gesture.busy||!start(`split-${i}`))return;e.stopPropagation();owner.current=svg;
            pointer.current={id:e.pointerId,kind:'split',index:i};svg?.setPointerCapture(e.pointerId);
          }}/>
      </g>)}
      {props.samples?.parametric_handles?.map(([x,y],i)=><circle key={i} cx={x*256} cy={256-y*256} r="5" fill="#f5e2a2"
        style={{cursor:inactive?'default':'ns-resize'}} onPointerDown={e=>{
          if(e.button!==0)return;const svg=e.currentTarget.ownerSVGElement;svg?.focus();
          if(gesture.busy||!start(`tone-${i}`))return;e.stopPropagation();owner.current=svg;
          pointer.current={id:e.pointerId,kind:'tone',index:i};svg?.setPointerCapture(e.pointerId);
        }}/>) }
    </svg>
    <small>拖动圆点调整明暗；底部三角点划分四个区域。参数曲线与点曲线叠加生效。</small>
    {keys.map((key,i)=><div key={key} style={{display:'flex',gap:6,alignItems:'center',marginTop:6}}>
      <label htmlFor={`parametric-${key}`} style={{minWidth:32}}>{names[i]}</label>
      <input id={`parametric-${key}`} type="range" min="-100" max="100" step="1" value={p[key]}
        style={{minWidth:0,flex:1}} disabled={inactive||(busy&&control.current!==key)||gesture.closing}
        {...rangeEvents(key)} onChange={e=>change({[key]:e.target.valueAsNumber},key)}/>
      <input aria-label={`${names[i]}数值`} type="number" min="-100" max="100" step="1" value={Math.round(p[key]*100)/100}
        style={{width:62}} disabled={inactive||busy} onChange={e=>{if(Number.isFinite(e.target.valueAsNumber))change({[key]:clamp(e.target.valueAsNumber,-100,100)});}}/>
      <button type="button" aria-label={`重置${names[i]}`} disabled={inactive||busy} onClick={()=>change({[key]:0})}>↺</button>
    </div>)}
    <details style={{marginTop:8}}><summary>分区位置</summary>
      {p.splits.map((value,i)=><div key={i} style={{display:'flex',alignItems:'center',gap:6}}>
        <label>分界 {i+1}</label>
        <input aria-label={`分界${i+1}滑杆`} type="range" min={(bounds[i]+.01)*100} max={(bounds[i+2]-.01)*100}
          step="0.1" value={value*100} style={{minWidth:0,flex:1}} disabled={inactive||(busy&&control.current!==`split-${i}`)||gesture.closing}
          {...rangeEvents(`split-${i}`)} onChange={e=>split(i,e.target.valueAsNumber/100,`split-${i}`)}/>
        <input aria-label={`分界${i+1}百分比`} type="number" step="0.1" min={(bounds[i]+.01)*100} max={(bounds[i+2]-.01)*100}
          value={Math.round(value*10000)/100} style={{width:62}} disabled={inactive||busy}
          onChange={e=>{if(Number.isFinite(e.target.valueAsNumber))split(i,e.target.valueAsNumber/100);}}/><span>%</span>
      </div>)}
      <button type="button" disabled={inactive||busy} onClick={()=>change({splits:[.25,.5,.75]})}>重置分区</button>
    </details>
    {busy&&<small>调整中；完成后合并为一次撤销。按 Esc 取消本次调整。</small>}
  </section>;
}
