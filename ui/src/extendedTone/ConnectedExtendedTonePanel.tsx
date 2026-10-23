import {useEffect,useRef,useState} from 'react';
import {ExtendedTonePanel} from './ExtendedTonePanel';
import {Readback,toneCancel,toneQuery,toneReadback,toneSend} from './nativePort';
export function ConnectedExtendedTonePanel({documentId,revision,disabled,available}:{documentId:string;revision:number;disabled:boolean;available:boolean}){
  const [state,setState]=useState<Readback|null>(null);const [error,setError]=useState('');
  const generation=useRef(0);const document=useRef(documentId);document.current=documentId;
  async function refresh(){const token=++generation.current;const doc=document.current;const next=await toneReadback();if(token!==generation.current||doc!==document.current||next.document_id!==doc)throw Error('照片或回读请求已变化，旧结果未覆盖当前状态');setState(next);return next;}
  useEffect(()=>{let alive=true;setState(null);if(!available){setError('当前引擎未提供扩展影调 ABI2，请使用完整配套安装包');return;}
    refresh().then(()=>{if(alive)setError('');}).catch(e=>{if(alive)setError(String(e));});
    return()=>{alive=false;++generation.current;};
  },[documentId,revision,available]);
  return <>{error&&<p role="alert">{error}</p>}{state?.document_id===documentId&&<ExtendedTonePanel documentId={documentId} spec={state.spec} revision={state.revision} monochrome={state.spec.monochrome} disabled={disabled||!state.available} reason={!state.available?'扩展影调 Rust 核心尚未安装':''} send={toneSend} query={toneQuery} refresh={async()=>{await refresh();}} readback={refresh} cancel={toneCancel}/>}</>;
}
