// SPDX-License-Identifier: GPL-3.0-or-later
import {useCallback,useEffect,useRef,useState} from 'react';
import {colorCaptureApi,INSPECTION_EDIT_INTENT} from '../native';
import type {PeopleAction,PeopleView} from '../people/model';
import type {CaptureUi} from '../colorCaptureController';
import type {CaptureDescriptor,CapturePoint} from '../captureModel';
import {createEyelashPicker} from './picker';
import type {Side} from './model';
/** Host renders ui.frame using the existing verified capture overlay and calls
 * presented only after that frame paints; normal canvas clicks never bypass it.
 */
export function useEyelashPicker(view:PeopleView|null,renderRevision:number,allowed:boolean,otherToolActive:boolean,
  submit:(command:PeopleAction)=>Promise<void>){
  const [side,setSide]=useState<Side>('left_upper');const selectedSide=useRef(side);selectedSide.current=side;
  const latest=useRef({view,renderRevision,allowed,submit});latest.current={view,renderRevision,allowed,submit};
  const owner=useRef<ReturnType<typeof createEyelashPicker>|null>(null);
  const [ui,setUi]=useState<CaptureUi>({phase:'off',frame:null,readout:null,point:null,message:''});
  const [size,setSize]=useState<CapturePoint['size']>(1);
  useEffect(()=>{
    let live=true;
    const picker=createEyelashPicker(colorCaptureApi,state=>{if(live)setUi(state);},()=>latest.current.view,command=>latest.current.submit(command),()=>selectedSide.current);
    owner.current=picker;picker.update(latest.current.allowed,latest.current.renderRevision);
    const cancel=()=>picker.cancel();
    const key=(event:KeyboardEvent)=>{if(event.key==='Escape')picker.cancel();};
    window.addEventListener(INSPECTION_EDIT_INTENT,cancel);window.addEventListener('keydown',key);
    return()=>{live=false;owner.current=null;picker.dispose();window.removeEventListener(INSPECTION_EDIT_INTENT,cancel);window.removeEventListener('keydown',key);};
  },[]);
  useEffect(()=>{owner.current?.update(allowed,renderRevision);},[view,allowed,renderRevision]);
  const active=['arming','painting','eligible','sampling'].includes(ui.phase);
  useEffect(()=>{if(otherToolActive&&active)owner.current?.cancel();},[otherToolActive,active]);
  const arm=useCallback(async()=>{if(!owner.current)throw Error('吸管尚未就绪');await owner.current.arm();},[]);
  const apply=useCallback(async()=>{if(!owner.current)throw Error('吸管尚未就绪');await owner.current.apply();},[]);
  const cancel=useCallback(()=>owner.current?.cancel(),[]);
  const presented=useCallback((d:CaptureDescriptor)=>owner.current?.presented(d)??Promise.resolve(false),[]);
  const pick=useCallback((point:CapturePoint)=>owner.current?.pick(point),[]);
  const failed=useCallback((error:unknown)=>owner.current?.failed(error),[]);
  return {side,setSide,ui,active,size,setSize,arm,apply,cancel,presented,pick,failed};
}
