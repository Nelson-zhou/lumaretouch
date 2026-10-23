import {Request, Receipt} from './model';
export type EnginePort={send:(message:Record<string,unknown>)=>void;subscribe:(listener:(event:Record<string,unknown>)=>void)=>()=>void};
export function extendedToneTransport(engine:EnginePort){
  function wait(send:()=>void,match:(e:Record<string,unknown>)=>boolean):Promise<unknown>{
    return new Promise((resolve,reject)=>{
      let timer:ReturnType<typeof setTimeout>|undefined;
      const unsubscribe=engine.subscribe(event=>{if(match(event)){if(timer)clearTimeout(timer);unsubscribe();resolve(event);}});
      timer=setTimeout(()=>{unsubscribe();reject(Error('引擎结果超时；请查询原操作，勿重发'));},10000);
      try{send();}catch(error){clearTimeout(timer);unsubscribe();reject(error);}
    });
  }
  return {
    send:(r:Request)=>wait(()=>engine.send({...r}),e=>e.event==='extended_tone_result'&&e.request_id===r.request_id) as Promise<Receipt>,
    query:(id:string)=>wait(()=>engine.send({cmd:'extended_tone_receipt',request_id:id}),e=>e.event==='extended_tone_receipt'&&e.request_id===id),
  };
}
