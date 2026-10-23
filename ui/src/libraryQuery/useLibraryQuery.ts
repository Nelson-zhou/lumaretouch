import {useEffect,useRef,useState} from 'react';
import {runSession,type SessionState} from '../native';
import {defaultQuery,type LibraryQuery} from './model';
/** Only the engine evaluates filters. A request acknowledgement is not a result. */
export function useLibraryQuery(strip:SessionState|null,refresh:()=>Promise<unknown>,refreshKey:string){
  const result=strip?.library_query;
  const [query,setQuery]=useState<LibraryQuery>(defaultQuery);
  const [pending,setPending]=useState(false),[error,setError]=useState('');
  const requested=useRef<string|null>(null),epoch=useRef<string|null>(null);
  useEffect(()=>{
    if(!result)return;
    if(epoch.current!==result.session_id){epoch.current=result.session_id;requested.current=null;setQuery(result.query);setPending(false);setError('');}
    else if(!requested.current||requested.current===result.request_id){setQuery(result.query);setError(result.error??'');setPending(false);requested.current=null;}
  },[result]);
  const change=(next:LibraryQuery)=>{
    if(!result)return;
    const requestId=crypto.randomUUID();requested.current=requestId;setQuery(next);setPending(true);setError('');
    void runSession('query',{query:next,requestId,sessionId:result?.session_id}).then(refresh).catch(e=>{
      if(requested.current!==requestId)return;
      requested.current=null;setPending(false);setError(String(e));if(result)setQuery(result.query);
    });
  };
  const lastRefresh=useRef(refreshKey);
  useEffect(()=>{
    if(lastRefresh.current===refreshKey)return;
    lastRefresh.current=refreshKey;
    if(result&&!pending)change(query);
  },[refreshKey]);
  useEffect(()=>{
    if(!pending)return;
    const id=requested.current;
    const timer=setTimeout(()=>{if(requested.current===id){setError('筛选结果尚未确认，请重试筛选；当前显示的是上次结果。');setPending(false);}},10000);
    return ()=>clearTimeout(timer);
  },[pending,query]);
  // Old engines are visibly unsupported, never silently simulate a successful query.
  const supported=!!result;
  const byId=new Map((strip?.docs??[]).map(d=>[d.document_id,d]));
  const docs=supported?(result.document_ids??[]).flatMap(id=>{const d=byId.get(id);return d?[d]:[];}):(strip?.docs??[]);
  return {query,change,docs,result,pending,error:supported?error:'当前引擎未提供组合筛选协议，请重启更新后的引擎。',supported};
}
