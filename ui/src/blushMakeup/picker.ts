// SPDX-License-Identifier: GPL-3.0-or-later
import {createColorCaptureController,type CaptureTransport,type CaptureUi} from '../colorCaptureController';
import type {PeopleView,PeopleAction} from '../people/model';
import {context,contextKey,rgb,OP} from './model';
/** Reuses verified producer capture, presentation acknowledgment and latest-click
 * sampling. Never samples a canvas screenshot or trusts a UI-generated source ID.
 * Proxy working-sRGB output is explicitly shown; not an original-resolution or
 * ungraded-source readout. Only final chosen colour is rounded to 8-bit RGB.
 */
export function createBlushPicker(api:CaptureTransport,publish:(state:CaptureUi)=>void,
  current:()=>PeopleView|null,submit:(command:PeopleAction)=>Promise<void>){
  const capture=createColorCaptureController(api,publish);
  let bound:{key:string;view:PeopleView}|null=null;
  function cancel(){bound=null;capture.cancel();}
  function update(allowed:boolean,renderRevision:number,reason='照片、人物或参数已变化，请重新取色'){
    const view=current();
    if(bound&&(!view||bound.key!==contextKey(view)))cancel();
    capture.updateContext({documentId:view?.binding.document_id??'',revision:renderRevision,allowed:allowed&&!!view&&Number.isSafeInteger(renderRevision)&&renderRevision>=0,reason});
  }
  async function arm(){
    const view=current();if(!view)throw Error('没有当前源照片');context(view);
    bound={key:contextKey(view),view:structuredClone(view)};
    await capture.arm();
  }
  async function apply(){
    const view=current(),state=capture.snapshot(),sample=state.readout,frame=state.frame?.descriptor;
    if(!bound||!view||bound.key!==contextKey(view)||state.phase!=='eligible'||!sample?.success||!frame||!sample.descriptor)throw Error('腮红取色来源已过期，请重新取色');
    const d=sample.descriptor;
    for(const key of ['capture_id','ticket','generation','seq','document_id','epoch','shm_instance','width','height'] as const)
      if(d[key]!==frame[key])throw Error('取色回执与呈现画面不匹配');
    if(d.document_id!==view.binding.document_id||d.domain!=='proxy-output'||d.profile!=='working-srgb'||d.quality!=='proxy-float-output')throw Error('腮红只接受本照片已锁定的 working-sRGB 浮点画面');
    const a=sample.analysis,mean=a?.mean_srgb;
    if(!mean||mean.length!==3||mean.some(v=>!Number.isFinite(v)||v<0||v>1)||!a||a.nonfinite_samples!==0||a.finite_samples!==a.samples||a.samples<1)throw Error('取色样本无效或超出可选 sRGB 色域');
    const command:PeopleAction={...context(bound.view),request_id:crypto.randomUUID(),action:'patch',payload:{patches:[{operation_id:OP,parameter_path:'/colour',unset:false,value:rgb(mean.map(v=>Math.round(v*255)))}]}};
    cancel(); // Prevent duplicate application; original people receipt owns retry/query.
    await submit(command);
  }
  return {arm,apply,cancel,update,presented:capture.presented,pick:capture.pick,snapshot:capture.snapshot,
    failed:capture.failed,dispose:()=>{bound=null;capture.dispose();}};
}
