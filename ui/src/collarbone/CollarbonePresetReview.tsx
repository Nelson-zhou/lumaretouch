// SPDX-License-Identifier: GPL-3.0-or-later
import {CollarboneTransferReview} from './CollarboneTransferReview';
import type {CollarbonePresetReview as Review} from './presetModel';
import {fetchCollarbonePresetImage} from './presetTransport';
import {requestCollarbonePresetImage,readCollarbonePresetImage} from '../native';
export function CollarbonePresetReview({value,id,token,reviewKey,onReady,disabled}:{value:Review;id:string;token:string;reviewKey:string;onReady:(key:string,ready:boolean)=>void;disabled?:boolean}){
 const load=(side:'before'|'after',live:()=>boolean)=>fetchCollarbonePresetImage({request:requestCollarbonePresetImage,read:readCollarbonePresetImage},
  {id,documentId:value.load_id,preflightToken:token,revision:value.visual.revision,side,sha256:value.visual[side].sha256,requestId:crypto.randomUUID()},value.visual[side],live);
 return <section aria-label="完整混合预设的当前目标审核">
  <p>审核整份冻结预设对当前照片的实际影响，不是源照片示例或仅锁骨叠加。人物范围来自本照片自己的审核，不随预设复制。</p>
  <CollarboneTransferReview value={value.visual} coverage={value.coverage} preflightToken={token} reviewKey={reviewKey} onReady={onReady} disabled={disabled} imageLoader={load} preset/>
 </section>;
}
