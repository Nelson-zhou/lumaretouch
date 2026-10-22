import {canReconcileEdit} from '../editReceipts';
import {ColorActionLaunch,type ColorActionControlsProps} from '../colorActions/ColorActionControls';
import {useEffect,useRef,useState} from 'react';
import {runLevels} from '../native';
import {LEVEL_CHANNELS,LEVEL_KEYS,changedLevel,levelsSignature,neutralBand,neutralLevels,levelsMidpoint,gammaFromMidpoint,
  type LevelsChannel,type LevelsSpec,type LevelKey} from '../levelsModel';
const names={master:'RGB',red:'红',green:'绿',blue:'蓝'};
const labels:Record<LevelKey,string>={input_black:'输入黑点',input_white:'输入白点',gamma:'Gamma',output_black:'输出黑点',output_white:'输出白点'};
function LevelNumber({value,label,onValue}:{value:number;label:string;onValue:(value:number)=>void}){
  const [text,setText]=useState(String(value)),focused=useRef(false),cancelled=useRef(false);
  useEffect(()=>{if(!focused.current)setText(String(value));},[value]);
  return <input type="number" aria-label={label} value={text} step="any"
    onFocus={e=>{focused.current=true;e.currentTarget.select();}} onChange={e=>setText(e.target.value)}
    onBlur={()=>{focused.current=false;setText(String(value));if(cancelled.current){cancelled.current=false;return;}
      onValue(text.trim()===''?NaN:Number(text));}}
    onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();
      if(e.key==='Escape'){cancelled.current=true;setText(String(value));e.currentTarget.blur();}}}/>;
}
export function LevelsEditor({value,documentId,snapshotId,documentRevision,disabled,result,onDone,note,picker}:{
  value?:LevelsSpec;documentId:string;snapshotId?:string;documentRevision:number;disabled:boolean;
  result?:{request_id:string;document_id:string;host_doc_rev:number;success:boolean;spec:LevelsSpec;error:string|null}|null;
  onDone:()=>void;note:(text:string)=>void;picker?:ColorActionControlsProps;
}){
  const [draft,setDraft]=useState(()=>structuredClone(value??neutralLevels()));
  const [channel,setChannel]=useState<LevelsChannel>('master');
  const authoritative=useRef<{value?:LevelsSpec;documentId:string;snapshotId?:string}>({value,documentId,snapshotId});
  authoritative.current={value,documentId,snapshotId};
  function restoreAuthoritative(){const current=authoritative.current;
    if(current.value&&current.documentId===documentId&&current.snapshotId===documentId)update(current.value);}
  const live=useRef(draft),pending=useRef<{id:string;signature:string}|null>(null);
  const drag=useRef<{id:string;before:LevelsSpec}|null>(null);
  const finishRef=useRef<(cancel?:boolean)=>void>(()=>{});
  useEffect(()=>{const blur=()=>finishRef.current();window.addEventListener('blur',blur);
    return()=>window.removeEventListener('blur',blur);},[]);
  function update(s:LevelsSpec){live.current=structuredClone(s);setDraft(live.current);}
  useEffect(()=>{if(drag.current||pending.current||!value||snapshotId!==documentId)return;
    update(value);
  },[value,snapshotId,documentId]);
  useEffect(()=>{
    if(!result||!value||!canReconcileEdit(pending.current?.id,result,documentId,snapshotId,documentRevision,true))return;
    pending.current=null;
    if(!result.success){drag.current=null;note(result.error??'色阶未提交');}
    if(!drag.current)update(value);
  },[result,documentId,snapshotId,documentRevision,value]);
  function submit(spec:LevelsSpec,gestureId:string=crypto.randomUUID(),interactive=false){
    const requestId=crypto.randomUUID();update(spec);
    pending.current={id:requestId,signature:levelsSignature(spec)};
    void runLevels('set',spec,documentId,gestureId,interactive,requestId).then(onDone).catch(error=>{
      note(String(error));if(pending.current?.id===requestId){pending.current=null;drag.current=null;restoreAuthoritative();}
    });
  }
  function begin(){if(!drag.current)drag.current={id:crypto.randomUUID(),before:structuredClone(live.current)};}
  function finish(cancel=false){const active=drag.current;if(!active)return;drag.current=null;
    submit(cancel?active.before:live.current,active.id,false);}
  finishRef.current=finish;
  function change(key:LevelKey,value:number){try{submit(changedLevel(live.current,channel,key,value),drag.current?.id,!!drag.current);}catch(e){note(String(e));}}
  return <fieldset disabled={disabled||!documentId||snapshotId!==documentId||!value} className="levelsEditor" style={{margin:0,padding:8,border:'1px solid #45454b',borderRadius:6}}>
    <legend>色阶</legend>
    {picker&&<div className="colorActionToolbar" data-spec-control="PC-32455-C-8ebf8ee682"><ColorActionLaunch {...picker} blocked={picker.blocked||!draft.enabled||!!drag.current||!!pending.current} action="levels_black"/>
      <ColorActionLaunch {...picker} blocked={picker.blocked||!draft.enabled||!!drag.current||!!pending.current} action="levels_white"/>
      <small>{draft.enabled?'RGB 黑白场取样作用于三通道；不是白平衡中性吸管。':'请先启用色阶，再使用黑白场吸管。'}</small></div>}
    <div style={{display:'flex',gap:4,marginBottom:8}}>
      {LEVEL_CHANNELS.map(c=><button type="button" key={c} aria-pressed={channel===c}
        onClick={()=>{finish();setChannel(c);}}>{names[c]}</button>)}
      <label><input type="checkbox" checked={draft.enabled} onChange={e=>{finish();submit({...structuredClone(live.current),enabled:e.target.checked});}}/>启用</label>
    </div>
    {LEVEL_KEYS.map(key=><label key={key} style={{display:'grid',gridTemplateColumns:'70px 1fr 66px',gap:6,alignItems:'center',margin:'6px 0'}}>
      <span>{labels[key]}</span>
      <input type="range" aria-label={`${names[channel]} ${labels[key]}`} value={draft[channel][key]}
        min={key==='gamma'?.1:0} max={key==='gamma'?10:1} step={key==='gamma'?.01:.001}
        onPointerDown={e=>{begin();e.currentTarget.setPointerCapture(e.pointerId);}} onPointerUp={()=>finish()} onPointerCancel={()=>finish(true)}
        onLostPointerCapture={()=>finish()} onBlur={()=>finish()}
        onKeyDown={e=>{if(e.key.startsWith('Arrow'))begin();if(e.key==='Escape'){e.preventDefault();finish(true);}}}
        onKeyUp={()=>finish()} onChange={e=>change(key,e.target.valueAsNumber)}/>
      <LevelNumber label={`${names[channel]} ${labels[key]} 数值`} value={draft[channel][key]}
        onValue={value=>change(key,value)}/>
    </label>)}
    <label style={{display:'grid',gridTemplateColumns:'1fr 90px',gap:6,margin:'8px 0'}}>
      输入灰点（由 Gamma 换算）
      <LevelNumber label={`${names[channel]} 输入灰点`} value={levelsMidpoint(draft[channel])}
        onValue={value=>{try{change('gamma',gammaFromMidpoint(live.current[channel],value));}catch(e){note(String(e));}}}/>
    </label>
    <div style={{display:'flex',gap:6}}>
      <button type="button" onClick={()=>{finish();submit({...structuredClone(live.current),[channel]:neutralBand()});}}>重置通道</button>
      <button type="button" onClick={()=>{finish();submit(neutralLevels());}}>重置全部</button>
    </div>
    <small>Gamma 大于 1 提亮；生效通道裁切输入范围。输出黑白点可倒置形成反相。</small>
  </fieldset>;
}
