import { useEffect, useState } from 'react';
import { CustomLutPanel, type LutSnapshot } from './CustomLutPanel';
import { customLutPort } from './nativePort';
export function ConnectedCustomLutPanel({documentId,assetId,amount,hostRevision}:{documentId:string;assetId:string|null;amount:number;hostRevision:number}) {
  const [snapshot,setSnapshot]=useState<LutSnapshot|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{let live=true;setSnapshot(null);
    void customLutPort.state().then(s=>{if(live&&s.document_id===documentId){setSnapshot(s);setError('');}}).catch(e=>{if(live)setError(String(e));});
    return()=>{live=false;customLutPort.cancel(documentId);};
  },[documentId,assetId,amount,hostRevision]);
  return <>{error&&<p role="alert">{error}</p>}{snapshot&&snapshot.document_id===documentId&&<CustomLutPanel port={customLutPort} snapshot={snapshot} onSnapshot={setSnapshot}/>}</>;
}
