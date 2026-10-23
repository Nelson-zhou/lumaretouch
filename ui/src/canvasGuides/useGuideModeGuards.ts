import {useLayoutEffect,useState} from 'react';
/** Real category editor visibility, not a guessed selected tool. The existing
 * people editor is an inline details panel; dialogs also suspend guide editing. */
export function useGuideModeGuards(){
  const [blocked,setBlocked]=useState(false);
  useLayoutEffect(()=>{
    const update=()=>setBlocked(Array.from(document.querySelectorAll<HTMLElement>('[data-guide-category-editor][open],[role="dialog"]:not(.liquifyWorkspace),dialog[open]'))
      .some(node=>!node.hidden&&node.getClientRects().length>0));
    const observer=new MutationObserver(update);observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['open','hidden','class','style']});
    document.addEventListener('toggle',update,true);window.addEventListener('resize',update);update();
    return()=>{observer.disconnect();document.removeEventListener('toggle',update,true);window.removeEventListener('resize',update);};
  },[]);
  return blocked;
}
