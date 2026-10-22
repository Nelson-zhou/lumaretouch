import {useMemo,useRef} from 'react';
import {ReferenceColorControls} from '../referenceColor/ReferenceColorControls';
import type {SelectedSampleReference} from '../sampleLibrary/model';
import {SemanticColourPanel} from './SemanticColourPanel';
import {createNativeSemanticColour} from './nativePort';
/** Separate PC32455 scene correction and PC32452 semantic creative transfer. */
export function ColourTransferTools({sourceDocumentId,currentPath,targets,enabled,semanticEnabled,selectedSample,refreshKey,onComplete}:{
 sourceDocumentId:string;currentPath:string;targets:string[];enabled:boolean;semanticEnabled:boolean;
 selectedSample:SelectedSampleReference|null;refreshKey:string;onComplete:()=>void;
}){
 const available=useRef(semanticEnabled);available.current=semanticEnabled;
 const port=useMemo(()=>createNativeSemanticColour(()=>available.current),[]);
 return <><ReferenceColorControls sourceDocumentId={sourceDocumentId} currentPath={currentPath} targets={targets} enabled={enabled} onComplete={onComplete}/>
  {semanticEnabled&&sourceDocumentId&&<SemanticColourPanel port={port} documentKey={sourceDocumentId} refreshKey={refreshKey} selectedSample={selectedSample} onChanged={onComplete}/>}</>;
}
