import {StaticGuideLines} from '../canvasGuides/GuideOverlay';
import type {GuideOwner} from '../canvasGuides/useCanvasGuides';
import type {DocState} from '../native';
import {useEffect,useLayoutEffect,useRef,useState} from 'react';
import type {PointerEvent as ReactPointerEvent} from 'react';
import type {ManualLiquifyOwner} from './useManualLiquifyWorkflow';
import {newStroke,type BrushSettings,type LiquifyStroke} from './model';
interface Gesture {pointer:number;stroke:LiquifyStroke;rect:DOMRect;started:number;position:[number,number];pressure:number;timer:ReturnType<typeof setInterval>}
export function LiquifyCanvas({owner,settings,showBefore,zoom,guides,guideSourceSize,guideCrop}:{guides?:GuideOwner;guideSourceSize?:[number,number];guideCrop?:DocState['crop'];owner:ManualLiquifyOwner;settings:BrushSettings;showBefore:boolean;zoom:number}){
  const {state,workflow}=owner,image=state.image;
  const node=useRef<HTMLDivElement|null>(null),review=useRef<HTMLImageElement|null>(null),gesture=useRef<Gesture|null>(null);
  const [reviewVisible,setReviewVisible]=useState(false);
  const [cursor,setCursor]=useState<[number,number]|null>(null),[loaded,setLoaded]=useState({after:'',before:'',protection:'',final:'',finalId:''});
  function cancel(message:string){const g=gesture.current;gesture.current=null;if(g)clearInterval(g.timer);workflow.gestureCancelled(message);}
  useEffect(()=>()=>{if(gesture.current){clearInterval(gesture.current.timer);gesture.current=null;}},[]);
  useEffect(()=>{
    const blur=()=>{if(gesture.current)cancel('窗口失去焦点，未保存本笔');};
    const visibility=()=>{if(document.hidden)blur();};
    window.addEventListener('blur',blur);document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener('blur',blur);document.removeEventListener('visibilitychange',visibility);};
  },[workflow]);
  useLayoutEffect(()=>{
    if(!state.strokeActive&&gesture.current){clearInterval(gesture.current.timer);gesture.current=null;}
  },[state.strokeActive,state.open]);
  useLayoutEffect(()=>{
    const element=review.current;setReviewVisible(false);
    if(!element)return;
    let intersecting=false;
    const update=()=>setReviewVisible(intersecting&&!document.hidden&&document.hasFocus());
    const observer=new IntersectionObserver(entries=>{
      const entry=entries.find(v=>v.target===element);
      intersecting=!!entry&&entry.isIntersecting&&entry.intersectionRatio>=.99;update();
    },{threshold:[0,.99,1]});
    observer.observe(element);document.addEventListener('visibilitychange',update);
    window.addEventListener('focus',update);window.addEventListener('blur',update);
    return()=>{observer.disconnect();document.removeEventListener('visibilitychange',update);
      window.removeEventListener('focus',update);window.removeEventListener('blur',update);};
  },[state.previewId,image?.final_review.after]);
  useLayoutEffect(()=>{
    if(!image||!state.previewId||showBefore||!reviewVisible||loaded.after!==image.after||loaded.before!==image.before||
      loaded.protection!==image.protection||loaded.final!==image.final_review.after||loaded.finalId!==state.previewId)return;
    let live=true,second=0;const first=requestAnimationFrame(()=>{second=requestAnimationFrame(()=>{
      if(live&&!document.hidden&&document.hasFocus()&&review.current?.complete&&review.current.naturalWidth>0)void workflow.presented(state.previewId!);
    });});
    return()=>{live=false;cancelAnimationFrame(first);cancelAnimationFrame(second);};
  },[image,state.previewId,showBefore,loaded,reviewVisible,workflow]);
  const position=(e:ReactPointerEvent<HTMLDivElement>):[number,number]|null=>{
    const r=e.currentTarget.getBoundingClientRect(),x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
    return r.width>0&&r.height>0&&x>=0&&x<=1&&y>=0&&y<=1?[x,y]:null;
  };
  const pressure=(e:ReactPointerEvent<HTMLDivElement>)=>e.pointerType==='pen'?Math.min(1,Math.max(0,e.pressure)):1;
  function append(g:Gesture,final=false){
    if(gesture.current!==g||!node.current)return;
    const r=node.current.getBoundingClientRect();
    if((['left','top','width','height'] as const).some(k=>Math.abs(r[k]-g.rect[k])>.5)){cancel('画布位置或缩放变化，已取消本笔');return;}
    const time=performance.now()-g.started;
    if(time>60000||g.stroke.points.length>=2048){cancel('本笔超过时长或路径预算，请改为更短笔划');return;}
    const last=g.stroke.points.at(-1)!;
    if(time-last[3]>1000){cancel('手势停顿过久，已取消本笔');return;}
    g.stroke={...g.stroke,points:[...g.stroke.points,[...g.position,g.pressure,time]]};
    workflow.stroke(g.stroke,final);
  }
  if(!image)return <div className="liquifyWaiting">正在生成绘制图与最终光学预览…</div>;
  const aspect=image.width/image.height;
  const stop=(e:ReactPointerEvent<HTMLDivElement>)=>{e.preventDefault();e.stopPropagation();};
  return <div style={{display:'grid',gridTemplateColumns:'minmax(0,1fr) minmax(0,1fr)',gap:14,flex:1,minHeight:220,alignItems:'start'}}>
    <section style={{minWidth:0}} aria-label="镜头与透视前的液化绘制区域">
      <strong>可绘制 · 镜头/透视之前</strong>
      <p><small>已含其他效果和已有液化；不是原图。保护蒙版只对应此绘制域。</small></p>
      <div className="liquifyViewport" style={{height:'min(55vh,520px)'}}><div ref={node} className="liquifyCanvas" style={{aspectRatio:aspect,width:`${zoom}%`}}
    role="application" aria-label="手动液化镜头与透视前画布"
    onPointerDown={e=>{
      stop(e);if(e.button!==0||gesture.current||showBefore)return;
      const p=position(e);if(!p||!workflow.beginStroke())return;
      const r=e.currentTarget.getBoundingClientRect(),stroke=newStroke(p,r.width,r.height,settings,pressure(e));
      const g:Gesture={pointer:e.pointerId,stroke,rect:r,started:performance.now(),position:p,pressure:pressure(e),timer:0 as unknown as ReturnType<typeof setInterval>};
      gesture.current=g;g.timer=setInterval(()=>{if(gesture.current===g)append(g);},50);
      setCursor(p);e.currentTarget.setPointerCapture(e.pointerId);workflow.stroke(stroke);
    }}
    onPointerMove={e=>{
      stop(e);const p=position(e);setCursor(p);const g=gesture.current;if(!g||g.pointer!==e.pointerId)return;
      if(!p){cancel('手势中心移出画布，已取消本笔');return;}
      g.position=p;g.pressure=pressure(e);const last=g.stroke.points.at(-1)!;
      if(Math.hypot((p[0]-last[0])*g.rect.width,(p[1]-last[1])*g.rect.height)>=1.5)append(g);
    }}
    onPointerUp={e=>{
      stop(e);const g=gesture.current;if(!g||g.pointer!==e.pointerId)return;
      const p=position(e);if(!p){cancel('手势中心移出画布，未保存本笔');return;}
      g.position=p; // Keep last non-up pressure: pointer-up reports zero on pens.
      append(g,true);if(gesture.current===g){clearInterval(g.timer);gesture.current=null;}
      if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);
    }}
    onPointerCancel={e=>{stop(e);if(gesture.current?.pointer===e.pointerId)cancel('指针手势已取消，未保存本笔');}}
    onLostPointerCapture={e=>{if(gesture.current?.pointer===e.pointerId)cancel('指针控制中断，未保存本笔');}}
    onPointerLeave={()=>{if(!gesture.current)setCursor(null);}}>
    <img src={image.before} alt="本笔之前的真实效果，尚未经过镜头与透视" className={showBefore?'':'concealed'}
      onLoad={()=>setLoaded(v=>({...v,before:image.before}))} onError={()=>workflow.failed('液化对比图无法显示')}/>
    <img src={image.after} alt="当前真实液化效果，尚未经过镜头与透视" className={showBefore?'concealed':''}
      onLoad={()=>setLoaded(v=>({...v,after:image.after}))} onError={()=>workflow.failed('液化输出无法显示')}/>
    <img src={image.protection} alt="红色冻结保护蒙版" className={settings.showMask&&!showBefore?'':'concealed'}
      onLoad={()=>setLoaded(v=>({...v,protection:image.protection}))} onError={()=>workflow.failed('冻结保护蒙版无法显示')}/>
    {guides&&!guides.hidden&&!showBefore&&guideSourceSize&&<StaticGuideLines state={guides.state} sourceSize={guideSourceSize} crop={guideCrop}/>}
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">{cursor&&!showBefore&&<>
      <ellipse cx={cursor[0]*100} cy={cursor[1]*100} rx={settings.size/2*Math.min(1,1/aspect)} ry={settings.size/2*Math.min(1,aspect)} className="liquifyCursor"/>
      <ellipse cx={cursor[0]*100} cy={cursor[1]*100} rx={settings.size/2*Math.min(1,1/aspect)*settings.density/100} ry={settings.size/2*Math.min(1,aspect)*settings.density/100} className="liquifyDensity"/>
    </>}</svg>
      </div></div>
    </section>
    <figure style={{margin:0,minWidth:0,padding:8,background:'#10151b',border:'1px solid #465463',borderRadius:6}} aria-label="最终光学效果，只读不能绘制">
      <figcaption><strong>只读 · 最终效果</strong><p><small>{image.optics_active?'已包含当前镜头/透视和同一笔液化':'镜头/透视为中性，最终效果与左侧当前图一致'}</small></p></figcaption>
      <img key={state.previewId??'pending'} ref={review} src={image.final_review.after} alt="同一笔液化经过镜头和透视后的最终只读效果" draggable={false}
        style={{display:'block',width:'100%',height:'min(36vh,320px)',objectFit:'contain',pointerEvents:'none',userSelect:'none'}}
        onLoad={e=>{if(e.currentTarget===review.current)setLoaded(v=>({...v,final:image.final_review.after,finalId:state.previewId??''}));}}
        onError={()=>workflow.failed('最终光学预览无法显示，未提交本笔')}/>
      <p role="status"><small>{reviewVisible?'此处只读，不接收笔迹。最终图显示后才会保存。':'请滚动使最终预览完整可见；不会在隐藏最终图时提交。'}</small></p>
    </figure>
  </div>;
}
