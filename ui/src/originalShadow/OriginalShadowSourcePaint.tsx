import {useEffect,useLayoutEffect,useRef,useState,type PointerEvent as ReactPointerEvent} from 'react';
import {SPILL_LIMITS,spillPaintSourceKey,spillSourcePoint,validSpillPaint,verifySpillImage,type SpillPaintGeometry as Geometry,type SpillPaintSource,type SpillStroke} from '../spillRemoval/model';

type Props={title:string;source:SpillPaintSource;strokes:SpillStroke[];disabled:boolean;onChange:(strokes:SpillStroke[])=>void;onReady:(ready:boolean)=>void;onGestureStart:()=>void};
type Gesture={pointer:number;geometry:Geometry;stroke:SpillStroke};
const geometry=(element:HTMLElement):Geometry=>{const {left,top,width,height}=element.getBoundingClientRect();return {left,top,width,height};};
const unchanged=(a:Geometry,b:Geometry)=>Math.abs(a.left-b.left)<.01&&Math.abs(a.top-b.top)<.01&&Math.abs(a.width-b.width)<.01&&Math.abs(a.height-b.height)<.01;

/** Only the immutable, verified effective SOURCE is paintable. No output inverse mapping.
 * Shared spill module imports are geometry/PNG validators only: no spill request,
 * owner, token acquisition or persisted coverage is used by this component.
 */
export function OriginalShadowSourcePaint({title,source,strokes,disabled,onChange,onReady,onGestureStart}:Props){
 const key=spillPaintSourceKey(source),stage=useRef<HTMLDivElement|null>(null),overlay=useRef<HTMLCanvasElement|null>(null);
 const sourceImage=useRef<HTMLImageElement|null>(null),coverageImage=useRef<HTMLImageElement|null>(null),baseline=useRef<Uint8ClampedArray|null>(null);
 const gesture=useRef<Gesture|null>(null),notify=useRef(onReady);notify.current=onReady;
 const change=useRef(onChange);change.current=onChange;
 const [verified,setVerified]=useState<'loading'|'ready'|'error'>('loading'),[loaded,setLoaded]=useState({source:false,coverage:false});
 const [maskReady,setMaskReady]=useState(false),[mode,setMode]=useState<'erase'|'restore'>('restore'),[radius,setRadius]=useState(.025),[opacity,setOpacity]=useState(1),[feather,setFeather]=useState(25);
 const [zoom,setZoom]=useState(1),[showOverlay,setShowOverlay]=useState(true),[draft,setDraft]=useState<SpillStroke|null>(null),[message,setMessage]=useState('');
 const ready=verified==='ready'&&loaded.source&&loaded.coverage&&maskReady,locked=disabled||!ready;
 const state=useRef({locked,strokes,key,ready});state.current={locked,strokes,key,ready};
 const cancel=()=>{gesture.current=null;setDraft(null);notify.current(state.current.ready);};
 useLayoutEffect(()=>{notify.current(false);return()=>notify.current(false);},[key]);
 useEffect(()=>{let live=true;baseline.current=null;setMaskReady(false);setVerified('loading');cancel();
  void Promise.all([verifySpillImage(source.image),verifySpillImage(source.coverage)]).then(results=>{if(live)setVerified(results.every(Boolean)?'ready':'error');},()=>{if(live)setVerified('error');});
  return()=>{live=false;};
 },[key]);
 useEffect(()=>{notify.current(ready);},[ready,key]);
 useEffect(()=>{
  if(verified!=='ready'||!loaded.source||!loaded.coverage||!coverageImage.current)return;
  try{
   const canvas=document.createElement('canvas');canvas.width=source.coverage.width;canvas.height=source.coverage.height;
   const context=canvas.getContext('2d');if(!context)throw Error('canvas unavailable');context.drawImage(coverageImage.current,0,0);
   const pixels=context.getImageData(0,0,canvas.width,canvas.height).data;
   for(let i=0;i<pixels.length;i+=4){if(pixels[i]!==pixels[i+1]||pixels[i]!==pixels[i+2]||pixels[i+3]!==255)throw Error('coverage must be opaque grayscale');}
   baseline.current=new Uint8ClampedArray(pixels);setMaskReady(true);
  }catch{baseline.current=null;setMaskReady(false);setVerified('error');}
 },[verified,loaded.source,loaded.coverage,key]);
 useEffect(()=>{
  const node=stage.current;if(!node)return;
  const abort=()=>{if(gesture.current){cancel();setMessage('视图或焦点已变化，未完成笔画已取消。');}};
  const observer=new ResizeObserver(abort);observer.observe(node);
  window.addEventListener('resize',abort);window.addEventListener('scroll',abort,true);window.addEventListener('blur',abort);
  document.addEventListener('visibilitychange',abort);
  return()=>{observer.disconnect();window.removeEventListener('resize',abort);window.removeEventListener('scroll',abort,true);window.removeEventListener('blur',abort);document.removeEventListener('visibilitychange',abort);gesture.current=null;};
 },[key]);
 useEffect(()=>{if(locked)cancel();},[locked]);
 useEffect(()=>{
  const canvas=overlay.current;if(!canvas)return;const context=canvas.getContext('2d');if(!context)return;
  context.clearRect(0,0,canvas.width,canvas.height);if(!ready||!baseline.current)return;
  const pixels=context.createImageData(canvas.width,canvas.height);
  for(let i=0;i<pixels.data.length;i+=4){pixels.data[i]=0;pixels.data[i+1]=210;pixels.data[i+2]=255;pixels.data[i+3]=baseline.current[i];}
  context.putImageData(pixels,0,0);
  // Bounded display-only approximation. Engine-rasterized coverage and the
  // required real before/after review, not this overlay, decide applied pixels.
  for(const stroke of [...strokes,...(draft?[draft]:[])]){
   const stamp=document.createElement('canvas');stamp.width=canvas.width;stamp.height=canvas.height;
   const brush=stamp.getContext('2d');if(!brush)continue;
   brush.scale(canvas.width/source.source.width,canvas.height/source.source.height);
   brush.lineCap='round';brush.lineJoin='round';brush.strokeStyle='rgb(0,210,255)';brush.fillStyle='rgb(0,210,255)';
   const r=stroke.radius*Math.min(source.source.width,source.source.height),layers=stroke.feather?8:1;
   for(let layer=0;layer<layers;layer++){
    const fraction=layers===1?1:1-(stroke.feather/100)*(layer/(layers-1));
    brush.globalAlpha=layers===1?1:1/layers;brush.lineWidth=Math.max(.00001,2*r*fraction);
    brush.beginPath();stroke.points.forEach(([x,y],index)=>{if(index===0)brush.moveTo(x*source.source.width,y*source.source.height);else brush.lineTo(x*source.source.width,y*source.source.height);});
    if(stroke.points.length===1){brush.arc(stroke.points[0][0]*source.source.width,stroke.points[0][1]*source.source.height,Math.max(.00001,r*fraction),0,Math.PI*2);brush.fill();}else brush.stroke();
   }
   const dab=brush.getImageData(0,0,stamp.width,stamp.height).data;
   for(let i=0;i<pixels.data.length;i+=4){const amount=dab[i+3]*stroke.opacity;pixels.data[i+3]=stroke.mode==='erase'?Math.max(0,pixels.data[i+3]-amount):Math.max(pixels.data[i+3],amount);}
  }
  context.putImageData(pixels,0,0);
 },[ready,strokes,draft,key]);
 function appendPoint(event:ReactPointerEvent<HTMLDivElement>):boolean{
  const active=gesture.current,node=stage.current;if(!active||!node||event.pointerId!==active.pointer||state.current.locked)return false;
  if(!unchanged(active.geometry,geometry(node))){cancel();setMessage('绘制区域发生变化，未完成笔画已取消。');return false;}
  const point=spillSourcePoint(event.clientX,event.clientY,active.geometry);if(!point){cancel();setMessage('指针离开完整源图，未完成笔画已取消。');return false;}
  const last=active.stroke.points[active.stroke.points.length-1];if(last[0]===point[0]&&last[1]===point[1])return true;
  const count=state.current.strokes.reduce((n,s)=>n+s.points.length,0);
  if(active.stroke.points.length>=SPILL_LIMITS.pointsPerStroke||count+active.stroke.points.length>=SPILL_LIMITS.points){cancel();setMessage('笔画点数达到安全上限，未完成笔画已取消；可缩短笔画。');return false;}
  active.stroke={...active.stroke,points:[...active.stroke.points,point]};setDraft(active.stroke);return true;
 }
 function start(event:ReactPointerEvent<HTMLDivElement>){
  if(locked||event.button!==0||!event.isPrimary||gesture.current||!stage.current)return;
  if(strokes.length>=SPILL_LIMITS.strokes||strokes.reduce((n,s)=>n+s.points.length,0)>=SPILL_LIMITS.points){setMessage('草稿已达到安全上限，请先撤销部分笔画。');return;}
  const rect=geometry(stage.current),point=spillSourcePoint(event.clientX,event.clientY,rect);if(!point)return;
  const stroke:SpillStroke={id:crypto.randomUUID().replace(/-/g,''),mode,points:[point],radius,opacity,feather};
  onGestureStart();gesture.current={pointer:event.pointerId,geometry:rect,stroke};setDraft(stroke);setMessage('');notify.current(false);
  event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault();
 }
 function finish(event:ReactPointerEvent<HTMLDivElement>){
  if(!appendPoint(event))return;const active=gesture.current;if(!active)return;
  const next=[...state.current.strokes,active.stroke];cancel();
  if(validSpillPaint({token:source.token,strokes:next})){change.current(next);notify.current(ready);}else{setMessage('笔画未通过边界校验，草稿未更新。');notify.current(ready);}
 }
 const imageLoaded=(which:'source'|'coverage',element:HTMLImageElement)=>{
  const expected=which==='source'?source.image:source.coverage,ok=element.naturalWidth===expected.width&&element.naturalHeight===expected.height;
  setLoaded(previous=>({...previous,[which]:ok}));if(!ok)setVerified('error');
 };
 return <section className="originalShadowSourcePaint" aria-label="当前完整源图原阴影画笔草稿">
  <strong>{title}：在完整源图上擦除 / 恢复范围</strong>
  <p>来源 {source.source.width} × {source.source.height}，显示缩略图 {source.image.width} × {source.image.height}。青色表示当前这一组样本范围；没有已保存范围时从空白开始，先恢复需要的区域。</p>
  <small>源图凭据最多五分钟有效。预览失败不会自动提交或丢弃草稿；若提示来源过期，重新读取会明确丢弃本次笔画。</small>
  <fieldset disabled={locked}><legend>仅编辑本次覆盖草稿</legend>
   <label><input type="radio" name={`shadow-brush-${source.token}-${title}`} checked={mode==='erase'} onChange={()=>{cancel();setMode('erase');}}/>擦除原阴影范围</label>
   <label><input type="radio" name={`shadow-brush-${source.token}-${title}`} checked={mode==='restore'} onChange={()=>{cancel();setMode('restore');}}/>恢复原阴影范围</label>
   <label>半径（源图短边 %）<input type="number" min={.01} max={50} step={.01} value={Number((radius*100).toFixed(4))} onChange={event=>{const n=event.target.valueAsNumber/100;if(Number.isFinite(n)&&n>=SPILL_LIMITS.radiusMin&&n<=SPILL_LIMITS.radiusMax){cancel();setRadius(n);}}}/></label>
   <label>不透明度<input type="range" min={0} max={1} step={.01} value={opacity} onChange={event=>{cancel();setOpacity(Number(event.target.value));}}/></label>
   <label>羽化<input type="range" min={0} max={100} step={1} value={feather} onChange={event=>{cancel();setFeather(Number(event.target.value));}}/></label>
   <button type="button" disabled={!strokes.length} onClick={()=>{cancel();onChange(strokes.slice(0,-1));}}>撤销上一笔草稿</button>
   <button type="button" disabled={!strokes.length} onClick={()=>{cancel();onChange([]);}}>重置本次草稿</button>
  </fieldset>
  <label>视图缩放<input type="range" min={1} max={4} step={.25} value={zoom} disabled={disabled} onChange={event=>{cancel();setZoom(Number(event.target.value));}}/> {Math.round(zoom*100)}%</label>
  <label><input type="checkbox" checked={showOverlay} onChange={event=>setShowOverlay(event.target.checked)}/>显示覆盖草稿叠层</label>
  <div className="originalShadowPaintViewport"><div className={`originalShadowPaintStage${locked?' isLocked':''}`} ref={stage} style={{width:`${zoom*100}%`,aspectRatio:`${source.source.width}/${source.source.height}`}}
   onPointerDown={start} onPointerMove={event=>{if(gesture.current)appendPoint(event);}} onPointerUp={finish}
   onPointerCancel={()=>{cancel();notify.current(ready);}} onLostPointerCapture={()=>{cancel();notify.current(ready);}} onContextMenu={event=>event.preventDefault()}>
   <img ref={sourceImage} src={`data:image/png;base64,${source.image.base64}`} alt="已冻结的当前完整来源，未经过输出裁切" draggable={false} onLoad={event=>imageLoaded('source',event.currentTarget)} onError={()=>setVerified('error')}/>
   <canvas ref={overlay} width={source.image.width} height={source.image.height} aria-hidden="true" style={{opacity:showOverlay?0.4:0}}/>
  </div></div>
  <img hidden ref={coverageImage} src={`data:image/png;base64,${source.coverage.base64}`} alt="" onLoad={event=>imageLoaded('coverage',event.currentTarget)} onError={()=>setVerified('error')}/>
  {!ready&&<p role="status">{verified==='error'?'源图或覆盖图的字节、浏览器加载、尺寸或灰度验证失败，不能绘制。请重新读取源图。':'正在校验当前源图与覆盖图…'}</p>}
  {message&&<p role="status">{message}</p>}
  <small>每组连同已保存对象最多 64 个对象和 8192 个坐标；引擎超限时拒绝，不丢弃草稿。已记录 {strokes.length} / {SPILL_LIMITS.strokes} 笔。擦除减去笔画覆盖；恢复取当前覆盖与笔画覆盖的较大值，重复半透明恢复不会无限累加。叠层羽化仅为近似草稿，不是已应用效果；恢复范围不证明此处确实为均匀明亮地面或原阴影。笔画使用真实源图尺寸，仍须审核实际前后图。缩放、滚动、失焦或指针取消会丢弃未完成笔画。</small>
 </section>;
}
