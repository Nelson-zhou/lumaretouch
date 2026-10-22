import {parseCaptureFrame} from '../captureFrame.ts';
import type {CaptureDescriptor,CaptureRegion} from '../captureModel';
import {COLOR_ACTION_NAMES,colorActionLimit,colorActionStage,validateColorReceipt,validateColorSample,validateColorPreview,validateColorCommit,
  type ColorAction,type ColorChannel,type ColorActionContext,type ColorActionRequest,type ColorActionState,type ColorActionTransport} from './model.ts';

interface Target {revision:number;region:CaptureRegion;delta:number}
interface CaptureOwner {
  id:string;ticket:string|null;documentId:string;contextKey:string;action:ColorAction;channel:ColorChannel;
  ack:Promise<boolean>|null;desired:Target|null;verified:number;probeRunning:boolean;finishWanted:boolean;revision:number;
}
const initial=():ColorActionState=>({phase:'idle',frame:null,action:null,channel:null,region:null,delta:0,sample:null,preview:null,request:null,message:''});
function bounded<T>(promise:Promise<T>,milliseconds:number):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('等待超时')),Math.max(1,milliseconds));})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}

/** A single App owner holds capture, latest-only probes and the one-shot commit receipt. */
export function createColorActionWorkflow(api:ColorActionTransport,options:{refresh:()=>Promise<void>;id?:()=>string;sleep?:(ms:number)=>Promise<void>;timeoutMs?:number}){
  const id=options.id??(()=>crypto.randomUUID().replaceAll('-',''));
  const sleep=options.sleep??((ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms)));
  const timeout=options.timeoutMs??15000;
  let state=initial(),context:ColorActionContext={enabled:false,documentId:'',contextKey:''};
  let owner:CaptureOwner|null=null,active=true,life=0,queryRunning=false;
  let paintTimer:ReturnType<typeof setTimeout>|undefined;
  const listeners=new Set<(next:ColorActionState)=>void>();
  const publish=(patch:Partial<ColorActionState>)=>{state={...state,...patch};if(active)listeners.forEach(listener=>listener(state));};
  const pending=()=>!!state.request&&['sending','waiting','uncertain'].includes(state.phase);
  const current=(o:CaptureOwner)=>active&&owner===o;
  const clearPaintTimer=()=>{if(paintTimer!==undefined)clearTimeout(paintTimer);paintTimer=undefined;};
  const release=(o:CaptureOwner)=>{void api.cancel(o.id,o.ticket,o.documentId).catch(()=>{/* A cancelled capture never submits. */});};
  function discard(){const old=owner;owner=null;clearPaintTimer();if(old){old.finishWanted=false;old.desired=null;release(old);}}
  function cancel(message='已取消，未修改照片'){
    if(pending()){publish({message:'定向调整已提交，正在确认原操作；不会重发或回滚'});return;}
    discard();publish({...initial(),message});
  }
  function failed(error:unknown){
    if(pending()){publish({message:`原操作仍待确认：${String(error)}`});return;}
    discard();publish({...initial(),phase:'failure',message:String(error)});
  }
  function updateContext(next:ColorActionContext){
    context=next;
    if(owner&&(!next.enabled||next.documentId!==owner.documentId||next.contextKey!==owner.contextKey)){
      if(pending())publish({frame:null,preview:null});
      cancel(next.reason||'照片或编辑上下文已改变，未提交的定向调整已取消');
    }
  }
  async function start(action:ColorAction,channel:ColorChannel='master'){
    if(!active||pending()||queryRunning)return;
    if(owner)cancel('已切换定向调整工具');
    if(!context.enabled||context.canStart===false||!context.documentId){publish({phase:'failure',message:context.reason||'请等待照片与引擎就绪'});return;}
    const o:CaptureOwner={id:id(),ticket:null,documentId:context.documentId,contextKey:context.contextKey,action,
      channel:action==='curve'?channel:'master',ack:null,desired:null,verified:0,probeRunning:false,finishWanted:false,revision:0};
    owner=o;publish({...initial(),phase:'arming',action,channel:o.channel,message:`正在冻结${COLOR_ACTION_NAMES[action]}输入…`});
    const deadline=Date.now()+timeout;
    try{
      const receipt=await bounded(api.arm(o.id,o.documentId,o.action,o.channel).then(reply=>{
        o.ticket=reply.ticket;if(!current(o))release(o);return reply;
      }),deadline-Date.now());
      if(!current(o))return;
      if(!/^[1-9]\d*$/.test(receipt.ticket))throw Error('定向调整票据无效');
      while(current(o)){
        if(Date.now()>=deadline)throw Error('冻结工具输入超时');
        const report=await bounded(api.status(o.id,receipt.ticket),deadline-Date.now());
        if(!current(o))return;
        if(['error','stale','idle'].includes(report.phase))throw Error(report.error||'工具输入已失效');
        if(report.capture_id!==o.id||report.ticket!==receipt.ticket)throw Error('工具输入身份不匹配');
        if(report.phase==='ready'){
          const d=report.descriptor;
          if(!d||d.capture_id!==o.id||d.ticket!==o.ticket||d.document_id!==o.documentId||d.domain!=='color-action-input'||
            d.picker_action!==o.action||d.picker_channel!==o.channel||d.source_stage!==colorActionStage(o.action,o.channel))throw Error('工具输入阶段或通道不匹配');
          const buffer=await bounded(api.frame(o.id,receipt.ticket),deadline-Date.now());
          if(!current(o))return;
          const frame=parseCaptureFrame(buffer,d,'color-action-input');
          publish({phase:'painting',frame,message:'正在显示冻结的工具输入，仅用于精确定位…'});
          paintTimer=setTimeout(()=>{if(current(o)&&state.phase==='painting')failed('工具输入未完成显示，请重新开始');},timeout);return;
        }
        if(report.phase!=='arming')throw Error('工具输入状态不一致，请重新开始');
        await bounded(sleep(100),deadline-Date.now());
      }
    }catch(error){if(current(o))failed(error);}
  }
  function presented(descriptor:CaptureDescriptor):Promise<boolean>{
    const o=owner;
    if(!o||!current(o)||!o.ticket||state.frame?.descriptor!==descriptor)return Promise.resolve(false);
    if(['ready','probing'].includes(state.phase))return Promise.resolve(true);
    if(state.phase!=='painting')return Promise.resolve(false);
    if(o.ack)return o.ack;
    o.ack=(async()=>{
      try{
        const receipt=await bounded(api.presented(o.id,o.ticket!,o.documentId),timeout);
        if(!current(o))return false;
        if(receipt.eligible!==true)throw Error('工具输入尚不能取样');
        clearPaintTimer();publish({phase:'ready',message:o.action==='curve'?'点击选点，上下拖动调整输出；松手提交一次，Esc 取消':
          o.action==='hsl'?'点击选色，左右拖动调整色相；松手提交一次，Esc 取消':'点击照片设置 RGB 黑场或白场，取样后自动应用一次'});return true;
      }catch(error){if(current(o))failed(error);return false;}
    })();return o.ack;
  }
  const requestFor=(o:CaptureOwner,target:Target,preview:boolean):ColorActionRequest=>({request_id:`color-${preview?'probe':'apply'}-${id()}`,
    capture_id:o.id,ticket:o.ticket!,document_id:o.documentId,action:o.action,channel:o.channel,region:{...target.region},delta:target.delta});
  async function poll(request:ColorActionRequest,preview:boolean,valid:()=>boolean){
    const deadline=Date.now()+timeout;
    while(valid()){
      if(Date.now()>=deadline)throw Error(preview?'工具预览超时，未提交修改':'等待原调整结果超时；不会重新提交');
      const packet=await bounded(api.result(request.request_id,preview),deadline-Date.now());
      if(!valid())return null;
      const result=validateColorReceipt(packet,request);if(result)return result;
      await bounded(sleep(100),deadline-Date.now());
    }
    return null;
  }
  async function query(request:ColorActionRequest){
    if(!active||queryRunning)return;
    const token=life;queryRunning=true;
    publish({phase:'waiting',request,message:'正在确认原定向调整的历史回执…'});
    try{
      const result=await poll(request,false,()=>active&&token===life);
      if(!result||!active||token!==life)return;
      if(!result.success){discard();publish({phase:'failure',frame:null,preview:null,message:typeof result.error==='string'?result.error:'定向调整未完成'});return;}
      validateColorCommit(result);const sample=validateColorSample(result.sample,request);
      discard();publish({frame:null,preview:null,sample});
      let refreshFailed=false;try{await bounded(options.refresh(),Math.min(timeout,3000));}catch{refreshFailed=true;}
      if(!active||token!==life)return;
      publish({phase:'success',message:(result.no_change?'本次调整未产生变化，未新增历史步骤':
        context.documentId===request.document_id?'定向调整已完成，可撤销一次恢复':'上一张照片的定向调整已完成')+(refreshFailed?'；状态刷新失败，请稍后刷新':'')});
    }catch(error){if(active&&token===life){discard();publish({phase:'uncertain',frame:null,preview:null,request,message:`结果未确认：${String(error)}`});}}
    finally{if(token===life)queryRunning=false;}
  }
  async function commit(o:CaptureOwner,target:Target){
    if(!current(o)||pending()||!o.finishWanted||o.verified!==target.revision||o.desired!==target)return;
    if(!context.enabled||context.documentId!==o.documentId||context.contextKey!==o.contextKey){cancel('编辑上下文变化，未提交修改');return;}
    o.finishWanted=false;
    const request=requestFor(o,target,false),token=life;
    // Publish ownership BEFORE invoking: our edit-intent event cannot cancel this commit.
    publish({phase:'sending',request,message:'正在应用一次定向调整…'});
    try{await bounded(api.submit(request,false),timeout);}catch{/* A failed send may have executed. Query ONLY this request. */}
    if(active&&token===life)await query(request);
  }
  async function pump(o:CaptureOwner){
    if(!current(o)||o.probeRunning||pending())return;
    o.probeRunning=true;
    try{
      while(current(o)&&!pending()&&o.desired&&o.verified!==o.desired.revision){
        const target=o.desired,request=requestFor(o,target,true);
        publish({phase:'probing',message:'正在计算真实工具阶段预览，尚未修改照片…'});
        let settled=false;
        try{
          // One in-flight probe and one replaceable latest target, never a pointer-event queue.
          try{await bounded(api.submit(request,true),timeout);}catch{/* Even a preview send may have executed; resolve its original receipt before another probe. */}
          const result=await poll(request,true,()=>current(o)&&!pending());
          if(!result||!current(o)||pending())return;
          settled=true;
          if(!result.success&&o.desired!==target)continue;
          if(!result.success)throw Error(typeof result.error==='string'?result.error:'取样不能用于本次调整');
          const sample=validateColorSample(result.sample,request),preview=validateColorPreview(result.preview);
          if(o.desired!==target){
            const latest=o.desired;
            if(latest&&['x','y','width','height'].every(key=>latest.region[key as keyof CaptureRegion]===target.region[key as keyof CaptureRegion]))
              publish({sample,preview,phase:'probing',message:'已显示最近完成的真实工具预览，正在计算最新手势…'});
            continue;
          }
          o.verified=target.revision;
          publish({phase:'ready',sample,preview,message:o.finishWanted?'预览已验证，正在应用…':'工具阶段预览已更新；点击只选点，拖动或滑杆松手才提交'});
          if(o.finishWanted){await commit(o,target);return;}
        }catch(error){
          if(!current(o)||pending())return;
          if(!settled){failed(`工具预览通信未确认，已取消本次取样，未提交修改：${String(error)}`);return;}
          if(o.desired!==target)continue;
          o.finishWanted=false;o.desired=null;
          publish({phase:'ready',sample:null,preview:null,message:`预览未通过，未修改照片：${String(error)}`});return;
        }
      }
    }finally{o.probeRunning=false;}
  }
  function target(region:CaptureRegion,delta:number,select=false){
    const o=owner,d=state.frame?.descriptor;
    if(!o||!current(o)||!o.ticket||pending()||!d||!['ready','probing'].includes(state.phase))return;
    if(![region.x,region.y,region.width,region.height].every(Number.isInteger)||region.x<0||region.y<0||region.width<1||region.height<1||
      region.width*region.height>121||region.x+region.width>d.width||region.y+region.height>d.height||!Number.isFinite(delta))return;
    const limit=colorActionLimit(o.action),value=Math.max(-limit,Math.min(limit,delta));
    o.finishWanted=false;o.desired={revision:++o.revision,region:{...region},delta:value};
    publish({region:{...region},delta:value,...(select?{sample:null,preview:null}:{})});void pump(o);
  }
  function finish(){
    const o=owner,target=o?.desired;
    if(!o||!target||pending()||!current(o))return;
    if((o.action==='curve'||o.action==='hsl')&&target.delta===0){o.finishWanted=false;return;}
    o.finishWanted=true;
    if(o.verified===target.revision)void commit(o,target);
    else publish({message:'正在等待最后一次预览；验证成功后自动应用，Esc 可取消'});
  }
  return {snapshot:()=>state,subscribe:(listener:(next:ColorActionState)=>void)=>{listeners.add(listener);return()=>{listeners.delete(listener);};},
    context:updateContext,start,cancel,failed,presented,select:(region:CaptureRegion)=>target(region,0,true),
    adjust:(delta:number)=>{if(state.region)target(state.region,delta);},finish,
    busy:pending,capturing:()=>!!owner,
    check:async()=>{if(active&&state.request&&!queryRunning&&state.phase==='uncertain')await query(state.request);},
    activate(){active=true;},
    stop(){const wasPending=pending();discard();active=false;++life;queryRunning=false;
      state=wasPending?{...state,phase:'uncertain',frame:null,preview:null,message:'等待被中断，只可查询原调整结果'}:initial();},
    acknowledgeAfterReload(){if(active&&!queryRunning&&state.phase==='uncertain'&&state.request&&context.enabled&&context.documentId!==state.request.document_id)
      publish({...initial(),message:'已重新打开照片；旧定向调整不会重发'});},
  };
}
