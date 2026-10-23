import {useEffect, useRef, useSyncExternalStore} from 'react';
import {createRecoveryWorkflow} from './model';
import {recoveryNativePort} from './nativePort';
/** App-lifetime polling, independent of whether ProjectWorkspace is visible. */
export function useProjectRecovery(projectId:string, open:boolean) {
  const owners=useRef<{workflow:ReturnType<typeof createRecoveryWorkflow>;auto:ReturnType<typeof createRecoveryWorkflow>}|null>(null);
  if (!owners.current) owners.current={workflow:createRecoveryWorkflow(recoveryNativePort),auto:createRecoveryWorkflow(recoveryNativePort)};
  const {workflow,auto}=owners.current;
  const autosave=useSyncExternalStore(auto.subscribe,auto.snapshot,auto.snapshot);
  useEffect(()=>{workflow.updateProject(projectId);auto.updateProject(projectId);},[projectId,workflow,auto]);
  useEffect(()=>{
    if (!open) return;
    let running=false, composing=false, lastInput=0;
    const pointers=new Set<number>();
    const down=(event:PointerEvent)=>{pointers.add(event.pointerId);lastInput=Date.now();};
    const up=(event:PointerEvent)=>{pointers.delete(event.pointerId);lastInput=Date.now();};
    const key=()=>{lastInput=Date.now();};
    const compositionStart=()=>{composing=true;};
    const compositionEnd=()=>{composing=false;lastInput=Date.now();};
    window.addEventListener('pointerdown',down,true);window.addEventListener('pointerup',up,true);
    window.addEventListener('pointercancel',up,true);window.addEventListener('keydown',key,true);
    window.addEventListener('compositionstart',compositionStart,true);window.addEventListener('compositionend',compositionEnd,true);
    const tick=async()=>{
      if(running||pointers.size||composing||Date.now()-lastInput<1000)return;running=true;
      try {
        if(auto.snapshot().phase==='uncertain'||auto.snapshot().phase==='working') await auto.read();
        else await auto.run('checkpoint');
      } finally {running=false;}
    };
    const timer=window.setInterval(()=>{void tick();},5000);
    void tick();return()=>{window.clearInterval(timer);
      window.removeEventListener('pointerdown',down,true);window.removeEventListener('pointerup',up,true);
      window.removeEventListener('pointercancel',up,true);window.removeEventListener('keydown',key,true);
      window.removeEventListener('compositionstart',compositionStart,true);window.removeEventListener('compositionend',compositionEnd,true);
    };
  },[open,projectId,auto]);
  return {workflow,autosave};
}
