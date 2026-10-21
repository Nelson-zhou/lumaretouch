import {useCallback,useEffect,useRef,useState} from 'react';
import {createColorCaptureController,type CaptureContext,type CaptureUi} from './colorCaptureController';
import {colorCaptureApi,INSPECTION_EDIT_INTENT} from './native';
import type {CaptureDescriptor,CapturePoint} from './captureModel';
export function useColorSampler(context:CaptureContext,otherToolActive:boolean){
  const [ui,setUi]=useState<CaptureUi>({phase:'off',frame:null,readout:null,point:null,message:''});
  const [size,setSize]=useState<CapturePoint['size']>(1);
  const ref=useRef<ReturnType<typeof createColorCaptureController>|null>(null);
  const latest=useRef(context);latest.current=context;
  useEffect(()=>{
    let live=true;
    const controller=createColorCaptureController(colorCaptureApi,state=>{if(live)setUi(state);});
    ref.current=controller;controller.updateContext(latest.current);
    const edit=()=>controller.cancel('图片正在调整，请重新锁定取色');
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape'&&controller.snapshot().phase!=='off')controller.cancel();};
    window.addEventListener(INSPECTION_EDIT_INTENT,edit);window.addEventListener('keydown',key);
    return ()=>{live=false;ref.current=null;controller.dispose();window.removeEventListener(INSPECTION_EDIT_INTENT,edit);window.removeEventListener('keydown',key);};
  },[]);
  useEffect(()=>{ref.current?.updateContext(context);},[context.documentId,context.revision,context.allowed,context.reason]);
  const active=['arming','painting','eligible','sampling'].includes(ui.phase);
  useEffect(()=>{if(otherToolActive&&active)ref.current?.cancel('已切换工具');},[otherToolActive,active]);
  const arm=useCallback(()=>{void ref.current?.arm();},[]);
  const cancel=useCallback(()=>ref.current?.cancel(),[]);
  const presented=useCallback((d:CaptureDescriptor)=>ref.current?.presented(d)??Promise.resolve(false),[]);
  const pick=useCallback((point:CapturePoint)=>ref.current?.pick(point),[]);
  const failed=useCallback((error:unknown)=>ref.current?.failed(error),[]);
  return {ui,active,size,setSize,arm,cancel,presented,pick,failed};
}
export type ColorSampler=ReturnType<typeof useColorSampler>;
