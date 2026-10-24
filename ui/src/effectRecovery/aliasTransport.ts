// SPDX-License-Identifier: GPL-3.0-or-later
import {validCollarboneImageMetadata,verifyCollarboneImage} from '../collarbone/transferModel';
import type {SpillImage} from '../spillRemoval/model';
import {recoveryObject,type RecoveryAliasExpectedImage,type RecoveryAliasImageRequest} from './aliasModel';
export type RecoveryAliasImageTransport={image:(request:RecoveryAliasImageRequest)=>Promise<unknown>;
  imageStatus:(previewId:string,requestId:string)=>Promise<unknown>};
type ImageProof={document_id:string;generation:string;recipe_document_id:string;recipe_revision:string};
/** Lazy, correlated, read-only image fetch. Retries never submit a recovery mutation. */
export async function fetchRecoveryAliasImage(api:RecoveryAliasImageTransport,request:RecoveryAliasImageRequest,
  expected:RecoveryAliasExpectedImage,live:()=>boolean,proof:ImageProof):Promise<SpillImage>{
  if(!validCollarboneImageMetadata(expected)||request.sha256!==expected.sha256)throw Error('共享来源恢复图像元数据不匹配');
  const deadline=Date.now()+30000;
  const bounded=<T,>(promise:Promise<T>):Promise<T>=>new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('读取审核图像超时，可重试只读读取。')),Math.max(1,deadline-Date.now()));
    promise.then(v=>{clearTimeout(timer);resolve(v);},e=>{clearTimeout(timer);reject(e);});});
  if(!live())throw Error('恢复审核已失效');
  await bounded(api.image({...request}));
  while(live()){
    const raw=await bounded(api.imageStatus(request.previewId,request.requestId));
    if(!live())throw Error('恢复审核已失效');
    if(!recoveryObject(raw)||raw.preview_id!==request.previewId||raw.request_id!==request.requestId)throw Error('恢复图像读取身份不匹配');
    if(raw.state==='image'){
      const value=raw.image;
      if(raw.protocol!==2||raw.capture_id!==request.captureId||raw.ticket!==request.ticket||raw.review_sha256!==request.reviewSha256
        ||raw.document_id!==proof.document_id||raw.generation!==proof.generation||raw.recipe_document_id!==proof.recipe_document_id||raw.recipe_revision!==proof.recipe_revision
        ||raw.member_document_id!==request.memberDocumentId||raw.member_revision!==request.memberRevision||raw.side!==request.side||raw.sha256!==request.sha256
        ||raw.success!==true||!recoveryObject(value)||value.mime!==expected.mime||value.width!==expected.width||value.height!==expected.height
        ||value.sha256!==expected.sha256||!await verifyCollarboneImage(value as unknown as SpillImage)||!live())throw Error('恢复图像摘要、来源或成员不一致');
      return value as unknown as SpillImage;
    }
    if(!['pending','running'].includes(String(raw.state))||Date.now()>=deadline)throw Error(typeof raw.error==='string'?raw.error:'恢复图像暂不可读取，请重试只读读取。');
    await bounded(new Promise<void>(resolve=>setTimeout(resolve,100)));
  }
  throw Error('恢复审核已失效');
}
