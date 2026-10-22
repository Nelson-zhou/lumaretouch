import {useLayoutEffect} from 'react';
import type {RefObject} from 'react';

/** Verify the rendered element, including its scrolling ancestors, at paint time.
 * IntersectionObserver alone can briefly retain an old intersection on scroll.
 * This is presentation evidence, not a claim that the user understood the image.
 */
function visibleImage(element:HTMLImageElement):boolean{
  if(!element.isConnected||document.visibilityState!=='visible'||!document.hasFocus())return false;
  const bounds=element.getBoundingClientRect();
  if(bounds.width<=0||bounds.height<=0)return false;
  let left=Math.max(0,bounds.left),right=Math.min(window.innerWidth,bounds.right);
  let top=Math.max(0,bounds.top),bottom=Math.min(window.innerHeight,bounds.bottom);
  for(let node:HTMLElement|null=element;node;node=node.parentElement){
    const style=window.getComputedStyle(node);
    if(node.hidden||style.display==='none'||style.visibility!=='visible'||Number(style.opacity)<=0)return false;
    if(node!==element){
      const rect=node.getBoundingClientRect();
      if(/auto|scroll|hidden|clip/.test(style.overflowX)){left=Math.max(left,rect.left+node.clientLeft);right=Math.min(right,rect.left+node.clientLeft+node.clientWidth);}
      if(/auto|scroll|hidden|clip/.test(style.overflowY)){top=Math.max(top,rect.top+node.clientTop);bottom=Math.min(bottom,rect.top+node.clientTop+node.clientHeight);}
    }
  }
  if(Math.max(0,right-left)*Math.max(0,bottom-top)<bounds.width*bounds.height*.99)return false;
  // Reject ordinary DOM occlusion, including another dialog over this result.
  return [[.1,.1],[.9,.1],[.5,.5],[.1,.9],[.9,.9]].every(([x,y])=>
    document.elementFromPoint(bounds.left+x*bounds.width,bounds.top+y*bounds.height)===element);
}

/** The exact current result must be loaded, focused and visible for two paints. */
export function useOutputPresentation({element,previewId,source,width,height,ready,onPresented}:{
  element:RefObject<HTMLImageElement|null>;previewId:string|null;source:string|undefined;
  width:number|undefined;height:number|undefined;ready:boolean;onPresented:(id:string)=>Promise<void>;
}){
  useLayoutEffect(()=>{
    const target=element.current;
    if(!ready||!target||!previewId||!source||!width||!height)return;
    let live=true,intersecting=false,requested=false,first=0,second=0;
    const cancelFrames=()=>{cancelAnimationFrame(first);cancelAnimationFrame(second);first=second=0;};
    const valid=()=>live&&!requested&&intersecting&&element.current===target&&
      target.dataset.opticsPreview===previewId&&target.getAttribute('src')===source&&target.complete&&
      target.naturalWidth===width&&target.naturalHeight===height&&visibleImage(target);
    const attempt=()=>{
      if(!valid()){cancelFrames();return;}
      if(first||second)return;
      first=requestAnimationFrame(()=>{
        first=0;if(!valid())return;
        second=requestAnimationFrame(()=>{
          second=0;if(!valid())return;
          requested=true;void onPresented(previewId);
        });
      });
    };
    const observer=new IntersectionObserver(entries=>{
      const entry=entries.find(item=>item.target===target);
      if(entry)intersecting=entry.isIntersecting&&entry.intersectionRatio>=.99;
      attempt();
    },{threshold:[0,.99,1]});
    observer.observe(target);
    document.addEventListener('visibilitychange',attempt);
    window.addEventListener('focus',attempt);window.addEventListener('blur',attempt);
    window.addEventListener('resize',attempt);document.addEventListener('scroll',attempt,true);
    return()=>{
      live=false;cancelFrames();observer.disconnect();
      document.removeEventListener('visibilitychange',attempt);
      window.removeEventListener('focus',attempt);window.removeEventListener('blur',attempt);
      window.removeEventListener('resize',attempt);document.removeEventListener('scroll',attempt,true);
    };
  },[element,previewId,source,width,height,ready,onPresented]);
}
