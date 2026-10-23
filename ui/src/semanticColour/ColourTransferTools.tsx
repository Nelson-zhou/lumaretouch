import {useMemo,useRef,useState} from 'react';
import {ReferenceColorControls} from '../referenceColor/ReferenceColorControls';
import type {SelectedSampleReference} from '../sampleLibrary/model';
import {SemanticColourPanel} from './SemanticColourPanel';
import {createNativeSemanticColour} from './nativePort';
/** Separate PC32455 scene correction and PC32452 semantic creative transfer. */
export function ColourTransferTools({sourceDocumentId,currentPath,targets,enabled,semanticEnabled,workflowEnabled,selectedSample,refreshKey,onComplete}:{
 sourceDocumentId:string;currentPath:string;targets:string[];enabled:boolean;semanticEnabled:boolean;workflowEnabled:boolean;
 selectedSample:SelectedSampleReference|null;refreshKey:string;onComplete:()=>void;
}){
 const available=useRef(semanticEnabled);available.current=semanticEnabled;
 const workflowAvailable=useRef(workflowEnabled);workflowAvailable.current=workflowEnabled;
 const port=useMemo(()=>createNativeSemanticColour(()=>available.current,()=>workflowAvailable.current),[]);
 const [semanticBusy,setSemanticBusy]=useState(false);
 return <><ReferenceColorControls sourceDocumentId={sourceDocumentId} currentPath={currentPath} targets={targets} enabled={enabled&&!semanticBusy} onComplete={onComplete}/>
  {semanticEnabled&&sourceDocumentId&&<SemanticColourPanel port={port} workflowEnabled={workflowEnabled} documentKey={sourceDocumentId} refreshKey={refreshKey} targets={targets} selectedSample={selectedSample} onChanged={onComplete} onWorkflowBusyChange={setSemanticBusy}/>}</>;
}
