import {useEffect} from 'react';
import type {EngineStatus} from '../native';
import {useSourcePatchWorkflow} from '../sourcePatch/useSourcePatchWorkflow';
import {useWhiteBalancePickerWorkflow} from '../whiteBalance/useWhiteBalancePicker';
import {useCloneStampWorkflow} from '../cloneStamp/useCloneStampWorkflow';
import {useLocalMaskWorkflow} from './useLocalMaskWorkflow';
import type {LocalMaskContext} from './workflow';
/** App-scoped owners survive panel collapse. Drawing modes never share a capture lease. */
export function useRetouchCaptureWorkflows(context:LocalMaskContext,caps:EngineStatus['ready_caps'],samplingKey:string,
  refresh:()=>Promise<void>,brushOn:boolean,pickFace:boolean){
  const sourcePatch=useSourcePatchWorkflow(context,refresh);
  const wbPicker=useWhiteBalancePickerWorkflow({...context,enabled:context.enabled&&!sourcePatch.active&&!sourcePatch.pending&&caps?.white_balance_capture_protocol===1,
    reason:caps?.white_balance_capture_protocol!==1?'当前引擎不支持白平衡输入取样，请更新匹配版本':'请结束其他操作，并切回单视图代理预览'},refresh);
  const cloneStamp=useCloneStampWorkflow({...context,samplingKey,enabled:context.enabled&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending&&caps?.clone_stamp_protocol===1,
    reason:caps?.clone_stamp_protocol!==1?'当前引擎不支持仿制图章，请更新匹配版本':context.reason},refresh);
  const localMasks=useLocalMaskWorkflow({...context,enabled:context.enabled&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending&&!cloneStamp.active&&!cloneStamp.pending&&caps?.local_masks_result_protocol===1,
    reason:caps?.local_masks_result_protocol!==1?'当前引擎不支持组合蒙版，请更新匹配版本':context.reason},refresh);
  useEffect(()=>{
    if(!brushOn&&!pickFace)return;
    for(const owner of [sourcePatch,wbPicker,cloneStamp,localMasks])
      if(owner.workflow.capturing()&&!owner.workflow.busy())owner.workflow.cancel('已切换工具，未提交的手势已取消');
  },[brushOn,pickFace,sourcePatch.workflow,wbPicker.workflow,cloneStamp.workflow,localMasks.workflow]);
  return {sourcePatch,wbPicker,cloneStamp,localMasks};
}
