import {useEffect,useRef,useState} from 'react';
import {PhotoDetailPanel} from './PhotoDetailPanel';
import {Readback,detailCancel,detailQuery,detailReadback,detailSend} from './nativePort';
export function ConnectedPhotoDetailPanel({documentId,revision,disabled,available}:{documentId:string;revision:number;disabled:boolean;available:boolean}){
  const [state,setState]=useState<Readback|null>(null);const [error,setError]=useState('');
  const generation=useRef(0);const document=useRef(documentId);document.current=documentId;
  async function refresh(){const token=++generation.current;const doc=document.current;const next=await detailReadback();if(token!==generation.current||doc!==document.current||next.document_id!==doc)throw Error('照片或回读请求已变化，旧结果未覆盖当前状态');setState(next);return next;}
  useEffect(()=>{let alive=true;setState(null);if(!available){setError('当前引擎未提供照片细节 ABI1，请使用完整配套安装包');return;}
    refresh().then(()=>{if(alive)setError('');}).catch(e=>{if(alive)setError(String(e));});
    return()=>{alive=false;++generation.current;};
  },[documentId,revision,available]);
  return <>{error&&<p role="alert">{error}</p>}{state?.document_id===documentId&&<PhotoDetailPanel documentId={documentId} spec={state.spec} revision={state.revision} disabled={disabled||!state.available} reason={!state.available?'照片细节 Rust 核心尚未安装':''} send={detailSend} query={detailQuery} refresh={async()=>{await refresh();}} readback={refresh} cancel={detailCancel}/>}</>;
}
