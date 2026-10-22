import {ParametricCurveEditor} from './ParametricCurveEditor';
import {ColorActionLaunch,type ColorActionControlsProps} from '../colorActions/ColorActionControls';
import {canReconcileEdit} from '../editReceipts';
import {curveSignature as signature, movedCurvePoint, matchesCurveResult, editableCurveSpec as copy, parametricCurveSpec, curveEditSnapshot, type EditableCurveSpec} from "../curveModel";
import {useEffect, useRef, useState} from 'react';
import {neutralCurves, previewCurves, runCurves, type CurveSpec, type CurveChannel, type CurvePreview} from '../native';

const channels:CurveChannel[]=['master','red','green','blue','luminance'];
const names=['RGB','红','绿','蓝','亮度'];
const colors=['#ddd','#ef7373','#79cd8d','#77aaff','#e8c779'];
const clamp=(v:number,lo=0,hi=1)=>Math.max(lo,Math.min(hi,v));
export function CurveEditor({value,documentId,snapshotId,documentRevision,disabled,parametricSupported,result,onDone,note,picker}:{value?:CurveSpec;documentId:string;snapshotId?:string;documentRevision:number;disabled:boolean;parametricSupported:boolean;picker?:ColorActionControlsProps;
  result?:{request_id:string;document_id:string;host_doc_rev:number;success:boolean;spec:CurveSpec}|null;
  error:string|null;onDone:()=>void;note:(s:string)=>void}){
  const [draft,setDraft]=useState<EditableCurveSpec>(()=>copy(value??neutralCurves()));
  const authoritative=useRef<{value?:CurveSpec;documentId:string;snapshotId?:string}>({value,documentId,snapshotId});
  authoritative.current={value,documentId,snapshotId};
  function restoreAuthoritative(){const current=authoritative.current;
    if(current.value&&current.documentId===documentId&&current.snapshotId===documentId)update(current.value);}
  const raw=useRef<CurveSpec>(structuredClone(value??neutralCurves()));
  const live=useRef(draft),pending=useRef<{id:string;signature:string}|null>(null);
  const [mode,setMode]=useState<'point'|'parametric'>('point');
  const paramActive=useRef(false);const [paramBusy,setParamBusy]=useState(false);const [resetToken,setResetToken]=useState(0);
  const paramBusyChanged=(busy:boolean)=>{paramActive.current=busy;setParamBusy(busy);};
  const [channel,setChannel]=useState<CurveChannel>('master');
  const [selected,setSelected]=useState(0);
  const [samples,setSamples]=useState<CurvePreview|null>(null);
  const drag=useRef<{id:string;before:CurveSpec;index:number;pointer:number}|null>(null);
  const previewRevision=useRef(0);
  const update=(s:CurveSpec)=>{const next=curveEditSnapshot(s);raw.current=next.raw;live.current=next.editable;setDraft(next.editable);};
  useEffect(()=>{
    if(drag.current||paramActive.current||pending.current||!value||snapshotId!==documentId)return;
    update(value);
  },[value,snapshotId,documentId]);
  useEffect(()=>{
    if(!result||!value||!canReconcileEdit(pending.current?.id,result,documentId,snapshotId,documentRevision,true))return;
    pending.current=null;
    if(!result.success){drag.current=null;paramActive.current=false;setParamBusy(false);setResetToken(v=>v+1);note('曲线未提交，请检查错误信息');}
    if(!drag.current&&!paramActive.current)update(value);
  },[result,documentId,snapshotId,documentRevision,value]);
  // Only a correlated result or this invocation's rejection may settle pending edits.
  disabled=disabled||!documentId||snapshotId!==documentId||!value;
  useEffect(()=>{
    const revision=++previewRevision.current;
    void previewCurves(mode==='parametric'&&parametricSupported?parametricCurveSpec(draft):draft).then(s=>{if(revision===previewRevision.current)setSamples(s);})
      .catch(e=>{if(revision===previewRevision.current)note(String(e));});
    return ()=>{++previewRevision.current;};
  },[draft,mode,parametricSupported]);
  const submit=(s:CurveSpec,id:string=crypto.randomUUID(),interactive=false)=>{
    const requestId=crypto.randomUUID();
    update(s);pending.current={id:requestId,signature:signature(copy(s))};
    return runCurves('set',s,id,interactive,requestId,documentId).then(()=>{onDone();}).catch(e=>{
      note(String(e));
      if(matchesCurveResult(pending.current?.id,requestId)) {
        pending.current=null;drag.current=null;paramActive.current=false;setParamBusy(false);setResetToken(v=>v+1);restoreAuthoritative();
      }
    });
  };
  const points=draft[channel], index=Math.min(selected,points.length-1),point=points[index];
  const move=(i:number,x:number,y:number,id?:string,interactive=false)=>{
    const s=copy(live.current),p=s[channel];
    p[i]=movedCurvePoint(p,i,x,y);
    submit(s,id,interactive);
  };
  const position=(e:React.PointerEvent<SVGSVGElement>)=>{
    const r=e.currentTarget.getBoundingClientRect();
    return [clamp((e.clientX-r.left)/r.width),clamp(1-(e.clientY-r.top)/r.height)];
  };
  const finish=(cancel=false)=>{
    const active=drag.current;if(!active)return;
    drag.current=null;
    // Final command is a queue barrier; cancellation restores the drag's starting recipe.
    submit(cancel?active.before:live.current,active.id,false);
  };
  const remove=()=>{if(index===0||index===points.length-1)return;
    const s=copy(live.current);s[channel].splice(index,1);setSelected(index-1);submit(s);};
  const yValues=samples?.[channel];
  return <fieldset disabled={disabled} className="curveEditor" style={{margin:0,padding:8,border:'1px solid #45454b',borderRadius:6}}>
    <legend>曲线</legend>
    <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:8}}>
      <button type="button" aria-pressed={mode==='point'} disabled={paramBusy||!!drag.current} onClick={()=>{if(picker?.owner.active)picker.owner.workflow.cancel();setMode('point');}}>点曲线</button>
      <button type="button" aria-pressed={mode==='parametric'} disabled={!parametricSupported||paramBusy||!!drag.current}
        title={parametricSupported?'四区域参数曲线':'当前引擎尚未支持参数曲线'} onClick={()=>{if(picker?.owner.active)picker.owner.workflow.cancel();setMode('parametric');}}>参数曲线</button>
      <label><input type="checkbox" checked={draft.enabled} disabled={paramBusy||!!drag.current}
        onChange={e=>submit({...copy(live.current),enabled:e.target.checked})}/>启用曲线</label>
      <button type="button" disabled={paramBusy||!!drag.current} onClick={()=>{setSelected(0);submit(neutralCurves());}}>重置全部</button>
    </div>
    {mode==='parametric'?<ParametricCurveEditor value={raw.current} samples={samples} disabled={disabled||!parametricSupported}
      resetToken={resetToken} submit={submit} onBusy={paramBusyChanged} note={note}/>:<>
    {channel==='luminance'&&<small>线性 sRGB 亮度 Y 保色曲线；非 Lab L*。黑场抬升使用中性补偿。</small>}
    {picker&&<div className="colorActionToolbar"><ColorActionLaunch {...picker} blocked={picker.blocked||!draft.enabled||paramBusy||!!drag.current||!!pending.current} action="curve" channel={channel}/>
      <small>{draft.enabled?'在照片中点击选点，上下拖动调整此通道输出。':'请先启用曲线，再使用定向调整。'}</small></div>}
    <div style={{display:'flex',gap:4,marginBottom:8}}>
      {channels.map((c,i)=><button type="button" key={c} aria-pressed={channel===c}
        style={{color:colors[i],fontWeight:channel===c?'bold':'normal'}}
        onClick={()=>{finish();if(picker?.owner.active&&picker.owner.state.action==='curve')picker.owner.workflow.cancel('曲线通道已切换，请重新在照片中选点');setChannel(c);setSelected(0);}}>{names[i]}</button>)}
    </div>
    <svg viewBox="0 0 256 256" role="img" aria-label={`${names[channels.indexOf(channel)]}点曲线，点击添加节点，拖动调整`} tabIndex={disabled?-1:0}
      style={{width:'100%',display:'block',background:'#202025',touchAction:'none',cursor:disabled?'default':'crosshair'}}
      onPointerDown={e=>{
        if(disabled||e.button!==0)return;
        const [x,y]=position(e),s=copy(live.current),p=s[channel];
        if(p.length>=64||p.some(([px])=>Math.abs(px-x)<2e-5))return;
        const i=p.findIndex(([px])=>px>x);if(i<=0)return;
        const before=copy(live.current);p.splice(i,0,[x,y]);setSelected(i);
        const id=crypto.randomUUID();drag.current={id,before,index:i,pointer:e.pointerId};
        e.currentTarget.setPointerCapture(e.pointerId);submit(s,id,true);
      }}
      onPointerMove={e=>{const a=drag.current;if(disabled||!a||a.pointer!==e.pointerId)return;
        const [x,y]=position(e);move(a.index,x,y,a.id,true);}}
      onPointerUp={e=>{if(drag.current?.pointer===e.pointerId)finish();}}
      onPointerCancel={()=>finish(true)} onLostPointerCapture={()=>finish()} onBlur={()=>finish()}
      onKeyDown={e=>{
        if(disabled)return;
        if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();e.stopPropagation();remove();}
        if(e.key.startsWith('Arrow')){e.preventDefault();e.stopPropagation();
          move(index,point[0]+(e.key==='ArrowRight'?.005:e.key==='ArrowLeft'?-.005:0),
            point[1]+(e.key==='ArrowUp'?.005:e.key==='ArrowDown'?-.005:0));}
      }}>
      {[64,128,192].map(n=><g key={n} stroke="#3a3a42"><path d={`M${n} 0V256 M0 ${n}H256`}/></g>)}
      <path d="M0 256L256 0" stroke="#62626a" strokeDasharray="3 4" fill="none"/>
      {yValues&&<polyline points={yValues.map((y,x)=>`${x},${256-y*256}`).join(' ')} fill="none" stroke={colors[channels.indexOf(channel)]} strokeWidth="2" pointerEvents="none"/>}
      {points.map(([x,y],i)=><circle key={i} cx={x*256} cy={256-y*256} r={i===index?5:4} fill={i===index?'#fff':'#999'}
        onPointerDown={e=>{if(disabled||e.button!==0)return;e.stopPropagation();setSelected(i);
          drag.current={id:crypto.randomUUID(),before:copy(live.current),index:i,pointer:e.pointerId};
          e.currentTarget.ownerSVGElement?.setPointerCapture(e.pointerId);}}/>)}
    </svg>
    <div style={{display:'flex',gap:6,marginTop:8}}>
      <label>输入<input type="number" min="0" max="1" step="0.001" style={{width:68}} value={point[0]}
        disabled={disabled||index===0||index===points.length-1} onChange={e=>{if(Number.isFinite(e.target.valueAsNumber))move(index,e.target.valueAsNumber,point[1]);}}/></label>
      <label>输出<input type="number" min="0" max="1" step="0.001" style={{width:68}} value={point[1]}
        onChange={e=>{if(Number.isFinite(e.target.valueAsNumber))move(index,point[0],e.target.valueAsNumber);}}/></label>
    </div>
    <div style={{display:'flex',gap:4,marginTop:8}}>
      <button type="button" disabled={disabled||index===0||index===points.length-1} onClick={remove}>删除节点</button>
      <button type="button" onClick={()=>{setSelected(0);submit({...copy(live.current),[channel]:[[0,0],[1,1]]});}}>重置当前</button>
    </div>
    <small>点击空白添加节点；选中后可用方向键微调。输入/输出为 0–1。</small>
    </>}
  </fieldset>;
}
