// SPDX-License-Identifier: GPL-3.0-or-later
import {useMemo,useRef,useSyncExternalStore} from 'react';
import {createHairColourPort} from './nativePort';
/** App lifetime owns original receipts, independently of the visible hair review. */
export function useHairColourPort(enabled:boolean,refresh:()=>Promise<void>){
  const live=useRef({enabled,refresh});live.current={enabled,refresh};
  const port=useMemo(()=>createHairColourPort(()=>live.current.enabled,()=>live.current.refresh()),[]);
  const state=useSyncExternalStore(port.subscribe,port.snapshot,port.snapshot);
  const check=()=>{void port.recover().catch(()=>undefined);};
  return {port,state,check};
}
