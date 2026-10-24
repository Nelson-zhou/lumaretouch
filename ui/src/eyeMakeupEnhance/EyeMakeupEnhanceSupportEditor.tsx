// SPDX-License-Identifier: GPL-3.0-or-later
import {useEffect, useRef, useState, type KeyboardEvent, type MouseEvent} from 'react';
import {verifiedImage, type EyeMakeupEnhanceView, type EyeReview, type Point, type Review, type Side, type SourceImage} from './model';
const emptyEye = (): EyeReview => ({makeup: [], exclusions: [], reference_a: null, reference_b: null,
  reference_confirmed: false, visible_makeup: false, unoccluded: false, ownership_confirmed: false, globe_lashes_brows_excluded: false});
const clearFlags = (eye: EyeReview): EyeReview => ({...eye, reference_confirmed: false, visible_makeup: false,
  unoccluded: false, ownership_confirmed: false, globe_lashes_brows_excluded: false});
type Field = 'makeup' | 'reference_a' | 'reference_b' | 'exclusion';
const flags = ['visible_makeup', 'unoccluded', 'ownership_confirmed', 'globe_lashes_brows_excluded'] as const;
const flagText = {visible_makeup: '我已看到原有眼妆，只圈选真实可见妆色，不猜测无妆或隐藏区域。',
  unoccluded: '这块妆区清晰无遮挡，已排除眼镜、头发、饰物、强反光与深阴影。',
  ownership_confirmed: '此范围仅属于当前选中人物的指定左右侧，不沿用其他工具或人物的审核。',
  globe_lashes_brows_excluded: '已排除整个眼球、眼线、全部睫毛、眉毛和其他人物；外伸睫毛也不包含。'};
/** Draft only until the canonical owner confirms this exact source-bound review. */
export function EyeMakeupEnhanceSupportEditor({report, disabled, onReview}: {
  report: EyeMakeupEnhanceView; disabled: boolean; onReview: (eyes: Review) => Promise<void>;
}) {
  const [image,setImage] = useState<SourceImage | null>(null), [loaded,setLoaded] = useState(false), [error,setError] = useState('');
  const [eyes,setEyes] = useState<Record<Side,EyeReview>>({left: emptyEye(),right: emptyEye()}), [side,setSide] = useState<Side>('left');
  const [field,setField] = useState<Field>('makeup'), [exclusion,setExclusion] = useState<Point[]>([]), [zoom,setZoom] = useState(2);
  const [cursor,setCursor] = useState<Point>([.5,.5]), [saving,setSaving] = useState(false);
  const alive = useRef(false), savingRef = useRef(false), source = report.source, proof = report.reference_proof;
  const key = proof ? `${proof.reference_request_id}:${proof.preview_sha256}` : 'missing';
  useEffect(() => {
    let current = true; alive.current = true; setLoaded(false);setImage(null);setError('');setEyes({left:emptyEye(),right:emptyEye()});setExclusion([]);
    void verifiedImage(report.source_preview,proof).then(v => {if(current) {setImage(v);
      const box=report.source_preview!.view_box;setCursor([(box[0]+box[2]/2)/(source.width-1),(box[1]+box[3]/2)/(source.height-1)]);}},
      e => {if(current)setError(String(e));});
    return () => {current=false;alive.current=false;};
  },[key]);
  const available = !disabled && !saving && loaded && !!image;
  const current = useRef({available,eyes,side,field,exclusion});current.current={available,eyes,side,field,exclusion};
  const eye = eyes[side];
  function change(next: EyeReview) {setEyes(v=>({...v,[side]:clearFlags(next)}));setError('');}
  function add(point: Point) {
    if(!current.current.available || point.some(n=>!Number.isFinite(n)||n<0||n>1))return;
    const old = field==='exclusion'?exclusion:eye[field]??[];
    if(old.length>=96) {setError('当前轮廓已达 96 点上限，请撤销或重新描绘。');return;}
    if(old.some(p=>p[0]===point[0]&&p[1]===point[1])) {setError('请勿重复顶点；保存时自动闭合。');return;}
    if(field==='exclusion') {setExclusion([...old,point]);change(eye);} else change({...eye,[field]:[...old,point]});
    setCursor(point);
  }
  function pick(event: MouseEvent<SVGSVGElement>) {
    if(event.button!==0||!available)return;const matrix=event.currentTarget.getScreenCTM();if(!matrix)return;
    const point=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse());
    add([point.x/(source.width-1),point.y/(source.height-1)]);
  }
  function keyboard(event: KeyboardEvent<SVGSVGElement>) {
    if(!available)return;const step=event.shiftKey?10:2;
    const movements:Record<string,Point>={ArrowLeft:[-step,0],ArrowRight:[step,0],ArrowUp:[0,-step],ArrowDown:[0,step]};
    if(movements[event.key]) {event.preventDefault();const [dx,dy]=movements[event.key];
      const box=report.source_preview!.view_box;
      setCursor(p=>[Math.max(Math.max(0,box[0]/(source.width-1)),Math.min(Math.min(1,(box[0]+box[2])/(source.width-1)),p[0]+dx/(source.width-1))),
        Math.max(Math.max(0,box[1]/(source.height-1)),Math.min(Math.min(1,(box[1]+box[3])/(source.height-1)),p[1]+dy/(source.height-1)))]);}
    if(event.key==='Enter'||event.key===' ') {event.preventDefault();add(cursor);}
  }
  function discard(lastOnly: boolean) {
    if(!available)return;
    const old=field==='exclusion'?exclusion:eye[field]??[], next=lastOnly?old.slice(0,-1):[];
    if(field==='exclusion') {setExclusion(next);change(eye);} else change({...eye,[field]:field==='makeup'?next:next.length?next:null});
  }
  const polygonReady = (p: Point[] | null) => !!p && p.length>=3;
  const refReady = polygonReady(eye.reference_a)&&polygonReady(eye.reference_b);
  const refsAbsent = eye.reference_a===null&&eye.reference_b===null;
  const canSave = available && exclusion.length===0 && polygonReady(eye.makeup) && flags.every(f=>eye[f])
    && (refsAbsent || refReady && eye.reference_confirmed);
  async function save() {
    if(!current.current.available||!canSave||savingRef.current)return;
    savingRef.current=true;setSaving(true);setError('');
    try {await onReview({[side]:structuredClone(eye)});} catch(e) {if(alive.current)setError(String(e));}
    finally {savingRef.current=false;if(alive.current)setSaving(false);}
  }
  const points=(value:Point[])=>value.map(p=>`${p[0]*(source.width-1)},${p[1]*(source.height-1)}`).join(' ');
  return <fieldset disabled={disabled||saving} aria-label="当前人物原有眼妆独立审核">
    <legend>原有眼妆可见范围与干净皮肤参考</legend>
    <p>这是未修饰来源裁切的参考图，不是全分辨率效果验收。左右指人物自身。先描绘确实存在的眼妆，再排除眼球、睫毛、眼线、眉毛和遮挡。不会检测或生成妆容。</p>
    <p>“增强 / 减淡”还需要同一只眼附近两块独立、无妆且光照相近的干净可见皮肤参考。没有可靠参考时可只审核妆区，使用单独饱和度、明度或立体度；减淡不是还原隐藏皮肤或完整卸妆。</p>
    {!loaded&&<p role="status">正在校验本次 PNG 字节和图像尺寸，尚不能保存审核。</p>}
    {image&&<div style={{overflow:'auto',maxHeight:520}}><div style={{position:'relative',width:`${zoom*100}%`,aspectRatio:`${image.width}/${image.height}`}}>
      <img key={key} src={image.url} alt="当前人物眼妆审核的未修饰来源裁切" draggable={false} style={{display:'block',width:'100%',height:'100%'}}
        onLoad={e=>{const correct=e.currentTarget.naturalWidth===image.width&&e.currentTarget.naturalHeight===image.height;setLoaded(correct);if(!correct)setError('图像实际解码尺寸与本次证明不符。');}}
        onError={()=>{setLoaded(false);setError('来源图像加载失败，不能审核。');}}/>
      <svg viewBox={image.viewBox} preserveAspectRatio="none" style={{position:'absolute',inset:0,width:'100%',height:'100%'}} tabIndex={0}
        role="img" aria-label="逐点描绘已有眼妆，方向键移动，回车添加点" aria-disabled={!available} onClick={pick} onKeyDown={keyboard}>
        {(['left','right'] as const).map(s=><g key={s} fill="none" strokeWidth={Math.max(1,source.width/1500)}>
          <polygon points={points(eyes[s].makeup)} stroke={s===side?'#22d3c5':'#819c96'}/>
          {eyes[s].reference_a&&<polygon points={points(eyes[s].reference_a!)} stroke="#ffd85a"/>}
          {eyes[s].reference_b&&<polygon points={points(eyes[s].reference_b!)} stroke="#a6b4ff"/>}
          {eyes[s].exclusions.map((p,i)=><polygon key={i} points={points(p)} stroke="#ff667f"/>)}</g>)}
        <polyline points={points(exclusion)} fill="none" stroke="#ff667f" strokeWidth={Math.max(1,source.width/1500)}/>
        <circle cx={cursor[0]*(source.width-1)} cy={cursor[1]*(source.height-1)} r={Math.max(2,source.width/800)} fill="none" stroke="white" strokeWidth={Math.max(1,source.width/1500)}/>
      </svg></div></div>}
    <label>参考放大<input type="range" min={1} max={8} step={.5} value={zoom} onChange={e=>setZoom(Number(e.target.value))}/></label>
    <label>人物自身侧别<select value={side} disabled={!available||exclusion.length>0} onChange={e=>setSide(e.target.value as Side)}><option value="left">左眼</option><option value="right">右眼</option></select></label>
    <label>描绘目标<select value={field} disabled={!available||exclusion.length>0} onChange={e=>setField(e.target.value as Field)}>
      <option value="makeup">原有妆区（青）</option><option value="reference_a">干净皮肤参考 A（黄）</option><option value="reference_b">干净皮肤参考 B（紫）</option><option value="exclusion">排除区（红）</option></select></label>
    <p>逐点点击，不要重复起点，保存时自动闭合。也可聚焦画布，用方向键移动 2 个源像素（Shift 为 10），Enter / 空格添加点。轮廓不能自交。</p>
    <button type="button" disabled={!available} onClick={()=>discard(true)}>撤销当前轮廓末点</button>
    <button type="button" disabled={!available} onClick={()=>discard(false)}>清空当前轮廓</button>
    <button type="button" disabled={!available||exclusion.length<3||eye.exclusions.length>=12} onClick={()=>{change({...eye,exclusions:[...eye.exclusions,exclusion]});setExclusion([]);}}>保存排除区</button>
    <button type="button" disabled={!available||!eye.exclusions.length} onClick={()=>change({...eye,exclusions:eye.exclusions.slice(0,-1)})}>撤销最后排除区</button>
    <button type="button" disabled={!available} onClick={()=>change({...eye,reference_a:null,reference_b:null})}>清除两块参考，仅审核独立子控件</button>
    {flags.map(flag=><label key={flag} style={{display:'block'}}><input type="checkbox" checked={eye[flag]} disabled={!available||!polygonReady(eye.makeup)||exclusion.length>0}
      onChange={e=>setEyes(v=>({...v,[side]:{...v[side],[flag]:e.target.checked}}))}/>{flagText[flag]}</label>)}
    {!refsAbsent&&<label><input type="checkbox" checked={eye.reference_confirmed} disabled={!available||!refReady||exclusion.length>0}
      onChange={e=>setEyes(v=>({...v,[side]:{...v[side],reference_confirmed:e.target.checked}}))}/>我确认 A、B 是同一眼附近两块独立无妆皮肤，无遮挡、无高光、无明显不同阴影；没有把妆色当作皮肤参考。</label>}
    <button type="button" disabled={!canSave} onClick={()=>void save()}>保存人物{side==='left'?'左':'右'}侧独立眼妆审核</button>
    <p>只保存此侧。已有另一侧审核保持不变；改动任何轮廓会清空此侧确认。审核仍不能绕过引擎的参考一致性、解剖保护、分辨率或预算拒绝。</p>
    {error&&<p role="alert">{error}</p>}
  </fieldset>;
}
