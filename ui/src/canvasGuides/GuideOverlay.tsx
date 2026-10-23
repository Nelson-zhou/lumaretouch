import {useLayoutEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import type {GuideOwner} from './useCanvasGuides';
import type {GuideState} from './model';
import {clipGuideSegment,displayToSource,guideKeyboardDelta,guideSegment,guideTransform,
  type GuideAxis,type GuideCrop,type GuideRect} from './geometry';
import './guides.css';

interface Drag {
  pointer:number; id:string; axis:GuideAxis; original:number; start:number;
  position:number; key:string; surface:SVGSVGElement;
}
interface Menu {id:string;left:number;top:number;key:string}
interface Draft {id:string;position:number;key:string}
const clamp=(value:number)=>Math.max(0,Math.min(1,value));

/** SVG overlays never enter the preview texture, source pixels, capture, or export. */
export function GuideOverlay({owner,clip,box,rect,crop,sourceSize,presentationDocumentId,presentationGeometry}:{
  owner:GuideOwner;clip:HTMLDivElement|null;box:GuideRect;rect:GuideRect;crop?:GuideCrop;
  sourceSize:readonly [number,number];presentationDocumentId:string|null;presentationGeometry?:string|null;
}){
  const surface=useRef<SVGSVGElement|null>(null),menuNode=useRef<HTMLDivElement|null>(null);
  const drag=useRef<Drag|null>(null),focusTarget=useRef<SVGGElement|null>(null);
  const [draft,setDraft]=useState<Draft|null>(null),[selected,setSelected]=useState<string|null>(null);
  const [menu,setMenu]=useState<Menu|null>(null);
  const transform=guideTransform(sourceSize,crop,rect);
  const shown=!!clip&&!!transform&&owner.state.visible&&!owner.hidden&&box.width>0&&box.height>0
    &&!!owner.documentId&&presentationDocumentId===owner.documentId&&!!owner.geometry&&presentationGeometry===owner.geometry;
  const editable=shown&&!owner.locked&&!owner.pending;
  // Include actual coordinates: resizing, scrolling, zooming, panning, cropping, a document
  // switch or an external guide update invalidates a gesture before it can be committed.
  const key=JSON.stringify([owner.documentId,owner.contextKey,owner.geometry,presentationDocumentId,presentationGeometry,box,rect,sourceSize,
    crop?.rect,crop?.rotation_degrees,crop?.out_full,shown,editable,owner.state.lines]);
  const current=useRef({owner,key,editable,transform,box});
  current.current={owner,key,editable,transform,box};
  const release=(active:Drag|null)=>{
    if(active?.surface.hasPointerCapture(active.pointer))active.surface.releasePointerCapture(active.pointer);
  };
  const cancel=()=>{const active=drag.current;drag.current=null;setDraft(null);release(active);};

  useLayoutEffect(()=>{
    cancel();setMenu(null);
    return()=>{const active=drag.current;drag.current=null;release(active);};
  },[key,clip]);
  useLayoutEffect(()=>{setSelected(null);focusTarget.current=null;},[owner.documentId]);
  useLayoutEffect(()=>{
    const blur=()=>{cancel();setMenu(null);};
    // A captured line may leave the visible crop and lose its focusable SVG child.
    // Escape must still cancel its local draft rather than commit an unseen move.
    const escape=(event:KeyboardEvent)=>{
      if(event.key==='Escape'&&drag.current){event.preventDefault();event.stopPropagation();cancel();}
    };
    const visibility=()=>{if(document.visibilityState!=='visible')blur();};
    window.addEventListener('blur',blur);
    window.addEventListener('keydown',escape,true);
    document.addEventListener('visibilitychange',visibility);
    return()=>{window.removeEventListener('blur',blur);window.removeEventListener('keydown',escape,true);
      document.removeEventListener('visibilitychange',visibility);};
  },[]);
  useLayoutEffect(()=>{
    if(!menu)return;
    menuNode.current?.querySelector<HTMLButtonElement>('button')?.focus({preventScroll:true});
    const dismiss=(event:PointerEvent)=>{
      if(!menuNode.current?.contains(event.target as Node))setMenu(null);
    };
    document.addEventListener('pointerdown',dismiss,true);
    return()=>document.removeEventListener('pointerdown',dismiss,true);
  },[menu]);

  if(!shown||!transform||!clip)return null;
  const viewport={left:0,top:0,width:box.width,height:box.height};
  const lines=owner.state.lines.flatMap((line,index)=>{
    const position=draft?.key===key&&draft.id===line.id?draft.position:line.position;
    const transformed=guideSegment(transform,line.axis,position);
    const segment=transformed?clipGuideSegment(transformed,viewport):null;
    return segment?[{...line,position,index,segment}]:[];
  });
  const closeMenu=()=>{setMenu(null);focusTarget.current?.focus({preventScroll:true});};
  const openMenu=(id:string,left:number,top:number)=>{
    if(!editable)return;
    cancel();setSelected(id);
    setMenu({id,left:Math.max(0,Math.min(left,box.width-190)),top:Math.max(0,Math.min(top,box.height-100)),key});
  };
  const updateDrag=(clientX:number,clientY:number)=>{
    const active=drag.current,now=current.current;
    if(!active||!now.editable||active.key!==now.key||!now.transform)return null;
    const point=displayToSource({x:clientX-now.box.left,y:clientY-now.box.top},now.transform);
    const value=active.axis==='vertical'?point.x:point.y;
    active.position=clamp(active.original+value-active.start);
    setDraft({id:active.id,position:active.position,key:active.key});
    return active;
  };

  return <>
    <svg ref={surface} className={`canvasGuideHitSurface${editable?'':' locked'}`} width={box.width} height={box.height}
      aria-label="可编辑参考线：拖动或方向键移动，Shift 加速，Delete 删除，Esc 取消拖动"
      onPointerMove={event=>{
        if(drag.current?.pointer!==event.pointerId)return;
        event.stopPropagation();updateDrag(event.clientX,event.clientY);
      }}
      onPointerUp={event=>{
        if(drag.current?.pointer!==event.pointerId)return;
        event.preventDefault();event.stopPropagation();
        const active=updateDrag(event.clientX,event.clientY),now=current.current;
        drag.current=null;setDraft(null);release(active);
        if(active&&active.key===now.key&&now.editable&&active.position!==active.original)now.owner.move(active.id,active.position);
      }}
      onPointerCancel={event=>{
        if(drag.current?.pointer===event.pointerId){event.stopPropagation();cancel();}
      }}
      onLostPointerCapture={event=>{if(drag.current?.pointer===event.pointerId)cancel();}}>
      {lines.map(line=>{
        const {start,end}=line.segment;
        const label=`${line.axis==='vertical'?'垂直':'水平'}参考线 ${line.index+1}，距原图${line.axis==='vertical'?'左侧':'顶部'} ${(line.position*100).toFixed(2)}%`;
        return <g key={line.id} tabIndex={editable?0:-1} role="slider" aria-label={label} aria-disabled={!editable}
          aria-orientation={line.axis==='vertical'?'horizontal':'vertical'} aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={Number((line.position*100).toFixed(2))} className="canvasGuideHandle"
          data-guide-id={line.id}
          onFocus={event=>{focusTarget.current=event.currentTarget;setSelected(line.id);}}
          onBlur={event=>{
            if(drag.current?.id===line.id)cancel();
            if(!menuNode.current?.contains(event.relatedTarget as Node))setSelected(null);
          }}
          onPointerDown={event=>{
            // Middle-button and non-guide space remain the Viewer's pan gesture.
            if(event.button!==0||!editable||!surface.current)return;
            event.preventDefault();event.stopPropagation();cancel();setMenu(null);
            event.currentTarget.focus({preventScroll:true});setSelected(line.id);
            const point=displayToSource({x:event.clientX-box.left,y:event.clientY-box.top},transform);
            const target=surface.current;
            try{target.setPointerCapture(event.pointerId);}catch{return;}
            drag.current={pointer:event.pointerId,id:line.id,axis:line.axis,original:line.position,
              start:line.axis==='vertical'?point.x:point.y,position:line.position,key,surface:target};
          }}
          onDoubleClick={event=>{event.preventDefault();event.stopPropagation();}}
          onContextMenu={event=>{
            if(!editable)return;
            event.preventDefault();event.stopPropagation();focusTarget.current=event.currentTarget;
            openMenu(line.id,event.clientX-box.left,event.clientY-box.top);
          }}
          onKeyDown={event=>{
            if(event.key==='Escape'){event.preventDefault();event.stopPropagation();cancel();setMenu(null);return;}
            if(!editable)return;
            if(event.key==='Delete'||event.key==='Backspace'){
              event.preventDefault();event.stopPropagation();cancel();setMenu(null);owner.remove(line.id);return;
            }
            if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){
              event.preventDefault();event.stopPropagation();openMenu(line.id,(start.x+end.x)/2,(start.y+end.y)/2);return;
            }
            if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)||drag.current)return;
            event.preventDefault();event.stopPropagation();
            const position=clamp(line.position+guideKeyboardDelta(transform,line.axis,event.key,event.shiftKey?10:1));
            if(Math.abs(position-line.position)>1e-12)owner.move(line.id,position);
          }}>
          <title>{label}；右键删除此线或清空全部</title>
          <line x1={start.x} y1={start.y} x2={end.x} y2={end.y}/>
        </g>;
      })}
    </svg>
    {menu&&menu.key===key&&editable&&<div ref={menuNode} className="canvasGuideMenu" role="menu"
      aria-label="参考线操作" style={{left:menu.left,top:menu.top}}
      onPointerDown={event=>event.stopPropagation()} onPointerMove={event=>event.stopPropagation()}
      onPointerUp={event=>event.stopPropagation()} onWheel={event=>event.stopPropagation()}
      onDoubleClick={event=>event.stopPropagation()} onContextMenu={event=>{event.preventDefault();event.stopPropagation();}}
      onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node))setMenu(null);}}
      onKeyDown={event=>{
        if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeMenu();return;}
        if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
        event.preventDefault();event.stopPropagation();
        const buttons=Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button'));
        const index=buttons.indexOf(document.activeElement as HTMLButtonElement);
        const next=event.key==='Home'?0:event.key==='End'?buttons.length-1:(index+(event.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;
        buttons[next]?.focus();
      }}>
      <button type="button" role="menuitem" onClick={()=>{owner.remove(menu.id);setMenu(null);}}>删除此参考线</button>
      <button type="button" role="menuitem" onClick={()=>{owner.clear();setMenu(null);}}>清空全部参考线</button>
    </div>}
    {createPortal(<svg className="canvasGuideVisuals" width={box.width} height={box.height} aria-hidden="true"
      data-guide-document={owner.documentId}>
      {lines.map(line=>{
        const {start,end}=line.segment;
        return <g key={line.id} className={selected===line.id?'selected':''}>
          <line className="canvasGuideShadow" x1={start.x} y1={start.y} x2={end.x} y2={end.y}/>
          <line className="canvasGuideStroke" x1={start.x} y1={start.y} x2={end.x} y2={end.y}/>
        </g>;
      })}
    </svg>,clip)}
  </>;
}

/** Read-only companion for the separate manual-liquify canvas. Parent places it over
 * the image's actual draw rectangle, not over the modal's letterboxed container. */
export function StaticGuideLines({state,sourceSize,crop}:{
  state:GuideState;sourceSize:readonly [number,number];crop?:GuideCrop;
}){
  const transform=guideTransform(sourceSize,crop,{left:0,top:0,width:1,height:1});
  if(!state.visible||!transform)return null;
  return <svg className="canvasGuideVisuals canvasGuideStatic" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
    {state.lines.map(line=>{
      const segment=guideSegment(transform,line.axis,line.position);
      if(!segment)return null;
      const {start,end}=segment;
      return <g key={line.id}>
        <line className="canvasGuideShadow" x1={start.x} y1={start.y} x2={end.x} y2={end.y}/>
        <line className="canvasGuideStroke" x1={start.x} y1={start.y} x2={end.x} y2={end.y}/>
      </g>;
    })}
  </svg>;
}
