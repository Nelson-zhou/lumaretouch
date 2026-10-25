// SPDX-License-Identifier: GPL-3.0-or-later
import {invoke} from '@tauri-apps/api/core';
import {open} from '@tauri-apps/plugin-dialog';
import {OPERATION_ID,canonical,freeze,hash,object,parseReceipt,sha256,validCurrent,
  type CancelRequest,type Current,type DonorCommand,type ExpressionCapability,type ExpressionPort,type Packet,type Receipt} from './model';

const EVENT='expression_replacement_result' as const;
export type CurrentReply=Readonly<{event:typeof EVENT;request_id:string}> & (
  {readonly phase:'current_ready';readonly current:Current} |
  {readonly phase:'pending'|'unknown'|'cancelling';readonly command_sha256?:string;readonly message:string} |
  {readonly phase:'cancelled'|'rejected';readonly no_write:true;readonly message:string}
);
export interface ExpressionNativePort extends ExpressionPort {
  refreshCapability:()=>Promise<ExpressionCapability>;
  acquireCurrent:(requestId:string)=>Promise<CurrentReply>;
  currentStatus:(requestId:string)=>Promise<CurrentReply>;
  cancelCurrent:(requestId:string,commandSha256:string)=>Promise<CurrentReply>;
}
interface PacketOwner {packet:Packet;dialog_open:boolean;cancel_requested:boolean;cancel_started:boolean;send_started:boolean;validated:Promise<void>}
const text=(value:unknown):value is string=>typeof value==='string'&&value.length>0&&value.length<=256&&!/[\u0000-\u001f\u007f]/.test(value);
const reason=(error:unknown)=>error instanceof Error?error.message:String(error);
function bounded<T>(promise:Promise<T>):Promise<T>{
  let timer:ReturnType<typeof setTimeout>|undefined;
  return Promise.race([promise,new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(Error('原生表情接口响应未确认，请查询原请求。')),10000);})])
    .finally(()=>{if(timer!==undefined)clearTimeout(timer);});
}
function envelope(value:unknown,requestId:string):Record<string,unknown>{
  if(!object(value)||value.event!==EVENT||value.request_id!==requestId)throw Error('表情回执外层身份不匹配。');
  return value;
}
function readCurrent(value:unknown,requestId:string):CurrentReply {
  const reply=envelope(value,requestId);
  if(reply.phase==='current_ready'&&validCurrent(reply.current))return freeze(reply) as CurrentReply;
  if(['pending','unknown','cancelling'].includes(String(reply.phase))&&typeof reply.message==='string'
    &&(reply.command_sha256===undefined||hash(reply.command_sha256)))return freeze(reply) as CurrentReply;
  if(['rejected','cancelled'].includes(String(reply.phase))&&reply.no_write===true&&typeof reply.message==='string')return freeze(reply) as CurrentReply;
  throw Error('当前照片获取回执不是可验证的状态。');
}
function localProgress(owner:PacketOwner,phase:'pending'|'unknown'|'cancelling',message:string):Receipt {
  const p=owner.packet;
  return freeze({version:1,operation_id:OPERATION_ID,request_id:p.command.request_id,command_sha256:p.command_sha256,action:p.command.action,binding:p.command.binding,phase,message});
}
/** Direct native envelopes only. No wrapper fallback or inferred success. */
export function createExpressionNativePort():ExpressionNativePort {
  let capability:ExpressionCapability=freeze({protocol:1,operation_id:OPERATION_ID,available:false,reason:'尚未核验原生表情模块能力。'});
  const owners=new Map<string,PacketOwner>(),currentRequests=new Set<string>(),releases=new Map<string,string>();
  function retained(id:string,digest:string):PacketOwner {
    const owner=owners.get(id);if(!owner||owner.packet.command_sha256!==digest)throw Error('没有匹配的原表情请求，不能重构或重发。');return owner;
  }
  async function remember(packet:Packet):Promise<PacketOwner>{
    if(!text(packet.command.request_id)||!hash(packet.command_sha256)||new TextEncoder().encode(packet.command_json).byteLength>256*1024||packet.command_json!==canonical(packet.command))throw Error('表情命令的对象、原始 JSON 或摘要不一致，未发送。');
    const existing=owners.get(packet.command.request_id);
    if(existing){if(existing.packet.command_sha256!==packet.command_sha256||existing.packet.command_json!==packet.command_json)throw Error('同一请求 ID 不能承载不同命令。');await existing.validated;return existing;}
    const owner:PacketOwner={packet:freeze(packet),dialog_open:false,cancel_requested:false,cancel_started:false,send_started:false,validated:Promise.resolve()};
    // Retain identity before asynchronous verification so a simultaneous cancel is not lost.
    owners.set(packet.command.request_id,owner);
    owner.validated=sha256(new TextEncoder().encode(packet.command_json)).then(digest=>{if(digest!==packet.command_sha256)throw Error('命令 SHA-256 不匹配，未发送。');});
    await owner.validated;return owner;
  }
  function receipt(value:unknown,owner:PacketOwner):Receipt {
    const result=envelope(value,owner.packet.command.request_id);
    if(result.receipt!==undefined){const parsed=parseReceipt(result.receipt,owner.packet);if(!parsed)throw Error('表情回执内容与保留命令不一致。');return parsed;}
    // A missing/evicted mailbox is absence of evidence, never a no-write proof.
    if(result.phase==='unknown'&&typeof result.message==='string')return localProgress(owner,'unknown',result.message);
    throw Error('表情请求缺少原操作回执。');
  }
  async function status(id:string,digest:string):Promise<Receipt>{
    const owner=retained(id,digest);
    if(owner.dialog_open)return localProgress(owner,owner.cancel_requested?'cancelling':'pending',owner.cancel_requested?'取消已请求；请关闭素材选择窗口。稍后选中的路径会被丢弃，尚未宣称任务已退出。':'素材选择窗口仍打开；尚未开始导入或分析。');
    if(!owner.send_started)return localProgress(owner,'pending','原请求正在准备发送，没有重新入队。');
    return receipt(await bounded(invoke<unknown>('expression_replacement_status',{requestId:id})),owner);
  }
  async function submit(owner:PacketOwner,path?:string):Promise<Receipt>{
    if(owner.send_started)return status(owner.packet.command.request_id,owner.packet.command_sha256);
    // Set before invoke: a rejected Promise is not evidence of a failed send.
    owner.send_started=true;
    const p=owner.packet,request={cmd:'expression_replacement',action:p.command.action,request_id:p.command.request_id,packet:p,...(path===undefined?{}:{path})};
    let result:Receipt;
    try{result=receipt(await bounded(invoke<unknown>('expression_replacement_request',{request})),owner);}
    catch{result=await status(p.command.request_id,p.command_sha256);}
    if(owner.cancel_requested&&p.command.action!=='apply'&&!['cancelled','rejected'].includes(result.phase))return cancel({version:1,operation_id:OPERATION_ID,request_id:p.command.request_id,command_sha256:p.command_sha256});
    return result;
  }
  async function chooseDonor(packet:Packet<DonorCommand>):Promise<Receipt>{
    const owner=await remember(packet);
    if(owner.dialog_open||owner.send_started)return status(packet.command.request_id,packet.command_sha256);
    if(owner.cancel_requested)return submit(owner);
    owner.dialog_open=true;let chosen:string|undefined;
    try{
      const result=await open({multiple:false,directory:false,title:'选择同场次本人表情素材',filters:[{name:'原始照片',extensions:['jpg','jpeg','png','tif','tiff','bmp','webp']}]});
      if(typeof result==='string'&&(/^(\/|[A-Za-z]:[\\/]|\\\\)/.test(result))&&!/[\u0000-\u001f\u007f]/.test(result)&&new TextEncoder().encode(result).byteLength<=4096)chosen=result;
    }catch{/* Native dialog failure is settled by the original no-selection host request, not a fabricated receipt. */}
    finally{owner.dialog_open=false;}
    // Cancellation during an OS chooser cannot force-close it or use a late selected path.
    return submit(owner,owner.cancel_requested?undefined:chosen);
  }
  async function cancel(request:CancelRequest):Promise<Receipt>{
    const owner=retained(request.request_id,request.command_sha256);
    if(request.version!==1||request.operation_id!==OPERATION_ID||owner.packet.command.action==='apply')throw Error('不能通过取消接口撤销已提交的副本保存。');
    owner.cancel_requested=true;
    if(owner.dialog_open||!owner.send_started)return localProgress(owner,'cancelling','取消已请求；等待素材窗口关闭并由原请求取得真实终态，不宣称强制停止。');
    if(owner.cancel_started)return status(request.request_id,request.command_sha256);
    owner.cancel_started=true;
    const ack=await bounded(invoke<unknown>('expression_replacement_cancel',{requestId:request.request_id,commandSha256:request.command_sha256}));
    if(!object(ack)||ack.requested!==true||ack.request_id!==request.request_id||ack.command_sha256!==request.command_sha256)throw Error('取消请求未获得匹配的接受回执；原任务终态仍待查询。');
    return status(request.request_id,request.command_sha256);
  }
  return {
    protocol:1,get capability(){return capability;},chooseDonor,cancel,status,
    preview:async packet=>submit(await remember(packet)),apply:async packet=>submit(await remember(packet)),
    async refreshCapability(){
      try{
        const value=await bounded(invoke<unknown>('expression_replacement_capability'));
        if(!object(value)||value.protocol!==1||value.operation_id!==OPERATION_ID||typeof value.available!=='boolean'||!(value.reason===null||typeof value.reason==='string'))throw Error('原生表情模块能力版本不匹配。');
        capability=freeze(value) as ExpressionCapability;
      }catch(error){capability=freeze({protocol:1,operation_id:OPERATION_ID,available:false,reason:reason(error)});}
      return capability;
    },
    async acquireCurrent(requestId){
      if(!text(requestId))throw Error('当前照片获取请求 ID 无效。');
      if(currentRequests.has(requestId))return readCurrent(await bounded(invoke<unknown>('expression_replacement_status',{requestId})),requestId);
      currentRequests.add(requestId);
      try{return readCurrent(await bounded(invoke<unknown>('expression_replacement_request',{request:{cmd:'expression_replacement',action:'current',request_id:requestId}})),requestId);}
      catch{return readCurrent(await bounded(invoke<unknown>('expression_replacement_status',{requestId})),requestId);}
    },
    async currentStatus(requestId){
      if(!currentRequests.has(requestId))throw Error('没有匹配的当前照片获取请求。');
      return readCurrent(await bounded(invoke<unknown>('expression_replacement_status',{requestId})),requestId);
    },
    async cancelCurrent(requestId,commandSha256){
      if(!currentRequests.has(requestId)||!hash(commandSha256))throw Error('来源获取取消缺少原生保留的原请求摘要。');
      const ack=await bounded(invoke<unknown>('expression_replacement_cancel',{requestId,commandSha256}));
      if(!object(ack)||ack.requested!==true||ack.request_id!==requestId||ack.command_sha256!==commandSha256)throw Error('来源获取取消尚未确认；不会宣称任务已退出。');
      return readCurrent(await bounded(invoke<unknown>('expression_replacement_status',{requestId})),requestId);
    },
    async releasePreview(previewToken){
      if(!text(previewToken))throw Error('候选释放令牌无效。');
      let id=releases.get(previewToken),value:unknown;
      if(id)value=await bounded(invoke<unknown>('expression_replacement_status',{requestId:id}));
      else{id=crypto.randomUUID();releases.set(previewToken,id);value=await bounded(invoke<unknown>('expression_replacement_request',{request:{cmd:'expression_replacement',action:'release',request_id:id,preview_token:previewToken}}));}
      const result=envelope(value,id);
      if(result.phase!=='released'||result.preview_token!==previewToken)throw Error('候选资源释放尚未得到匹配完成回执；由宿主保留原清理身份。');
    },
  };
}
