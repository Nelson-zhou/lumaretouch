import {useSkyReplacementWorkflow,type SkyReplacementOwner} from '../skyReplacement/useSkyReplacementWorkflow';
import {useOpticsWorkflow,type OpticsOwner} from '../optics/useOpticsWorkflow';
import {useStudioBackgroundWorkflow,type StudioOwner} from '../studioBackground/useStudioBackgroundWorkflow';
import {useEffect,useRef} from 'react';
import {useManualLiquifyWorkflow,type ManualLiquifyOwner} from '../manualLiquify/useManualLiquifyWorkflow';
import {useColorActionPicker} from '../colorActions/useColorActionPicker';
import type {EngineStatus} from '../native';
import {useSourcePatchWorkflow} from '../sourcePatch/useSourcePatchWorkflow';
import {useWhiteBalancePickerWorkflow} from '../whiteBalance/useWhiteBalancePicker';
import {useCloneStampWorkflow} from '../cloneStamp/useCloneStampWorkflow';
import {useLocalMaskWorkflow} from './useLocalMaskWorkflow';
import type {LocalMaskContext} from './workflow';
import {useEffectRecoveryWorkflow} from '../effectRecovery/useEffectRecoveryWorkflow';
import type {RecoveryReport} from '../effectRecovery/model';
import {useLiveGradeWorkflow,type LiveGradeOwner} from './useLiveGradeWorkflow';
/** App-scoped owners survive panel collapse. Drawing modes never share a capture lease. */
export function useRetouchCaptureWorkflows(context:LocalMaskContext,caps:EngineStatus['ready_caps'],samplingKey:string,
  refresh:()=>Promise<void>,brushOn:boolean,pickFace:boolean,
  recoveryOptions:{report?:RecoveryReport;prepare:()=>void}){
  const opticsOwner=useRef<OpticsOwner|null>(null),skyOwner=useRef<SkyReplacementOwner|null>(null);
  const studioOwner=useRef<StudioOwner|null>(null),liveOwner=useRef<LiveGradeOwner|null>(null),manualOwner=useRef<ManualLiquifyOwner|null>(null);
  const common={...context,enabled:context.enabled&&!skyOwner.current?.active&&!skyOwner.current?.pending&&!opticsOwner.current?.active&&!opticsOwner.current?.pending&&!studioOwner.current?.active&&!studioOwner.current?.pending&&!manualOwner.current?.active&&!manualOwner.current?.pending};
  const sourcePatch=useSourcePatchWorkflow(common,refresh);
  const wbPicker=useWhiteBalancePickerWorkflow({...common,enabled:common.enabled&&!sourcePatch.active&&!sourcePatch.pending&&caps?.white_balance_capture_protocol===1,
    reason:caps?.white_balance_capture_protocol!==1?'当前引擎不支持白平衡输入取样，请更新匹配版本':'请结束其他操作，并切回单视图代理预览'},refresh);
  const cloneStamp=useCloneStampWorkflow({...common,samplingKey,enabled:common.enabled&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending&&caps?.clone_stamp_protocol===1,
    reason:caps?.clone_stamp_protocol!==1?'当前引擎不支持仿制图章，请更新匹配版本':context.reason},refresh);
  const localMasks=useLocalMaskWorkflow({...common,enabled:common.enabled&&!sourcePatch.active&&!sourcePatch.pending&&!wbPicker.active&&!wbPicker.pending&&!cloneStamp.active&&!cloneStamp.pending&&caps?.local_masks_result_protocol===1,
    reason:caps?.local_masks_result_protocol!==1?'当前引擎不支持组合蒙版，请更新匹配版本':context.reason},refresh);
  const colorPicker=useColorActionPicker({...common,enabled:common.enabled&&!sourcePatch.pending&&!wbPicker.pending&&!cloneStamp.pending&&!localMasks.pending&&
    caps?.color_picker_capture_protocol===1&&caps?.color_picker_result_protocol===1,
    reason:caps?.color_picker_capture_protocol!==1||caps?.color_picker_result_protocol!==1?'当前引擎不支持定向色彩调整，请更新匹配版本':context.reason},refresh);
  const otherCapture=sourcePatch.active||sourcePatch.pending||wbPicker.active||wbPicker.pending||cloneStamp.active||cloneStamp.pending||localMasks.active||localMasks.pending||colorPicker.active||colorPicker.pending;
  const recovery=useEffectRecoveryWorkflow({...common,enabled:common.enabled&&!otherCapture&&!liveOwner.current?.workflow.busy()&&caps?.effect_recovery_protocol===1,
    reason:caps?.effect_recovery_protocol!==1?'当前引擎不支持专属恢复画笔，请更新匹配版本':context.reason},refresh,recoveryOptions.report,recoveryOptions.prepare);
  const liveGrade=useLiveGradeWorkflow({documentId:context.documentId,canStart:context.canStart,
    enabled:common.enabled&&!otherCapture&&!recovery.active&&!recovery.pending&&caps?.local_grade_live_protocol===1},refresh);
  liveOwner.current=liveGrade;
  const manual=useManualLiquifyWorkflow({...context,enabled:context.enabled&&!skyOwner.current?.active&&!skyOwner.current?.pending&&!opticsOwner.current?.active&&!opticsOwner.current?.pending&&!studioOwner.current?.active&&!studioOwner.current?.pending&&!otherCapture&&!recovery.active&&!recovery.pending&&!liveGrade.busy&&caps?.manual_liquify_protocol===1&&caps?.manual_liquify_preview_protocol===2,
    reason:caps?.manual_liquify_protocol!==1||caps?.manual_liquify_preview_protocol!==2?'当前引擎不支持手动液化，请更新匹配版本':context.reason},refresh,recoveryOptions.prepare);
  manualOwner.current=manual;
  const studio=useStudioBackgroundWorkflow({...context,enabled:context.enabled&&!skyOwner.current?.active&&!skyOwner.current?.pending&&!opticsOwner.current?.active&&!opticsOwner.current?.pending&&!otherCapture&&!recovery.active&&!recovery.pending&&!manual.active&&!manual.pending&&!liveGrade.busy&&caps?.studio_background_protocol===1},refresh,recoveryOptions.prepare);
  studioOwner.current=studio;
  const optics=useOpticsWorkflow({...context,enabled:context.enabled&&!skyOwner.current?.active&&!skyOwner.current?.pending&&!otherCapture&&!recovery.active&&!recovery.pending&&!manual.active&&!manual.pending&&!studio.active&&!studio.pending&&!liveGrade.busy&&caps?.optics_protocol===1},refresh,recoveryOptions.prepare);
  opticsOwner.current=optics;
  const sky=useSkyReplacementWorkflow({...context,enabled:context.enabled&&!otherCapture&&!recovery.active&&!recovery.pending&&!manual.active&&!manual.pending&&!studio.active&&!studio.pending&&!optics.active&&!optics.pending&&!liveGrade.busy&&caps?.sky_replacement_protocol===1,
    reason:caps?.sky_replacement_protocol!==1?"当前引擎不支持换天空，请更新匹配版本":context.reason},refresh,recoveryOptions.prepare);
  skyOwner.current=sky;
  useEffect(()=>{
    if(!brushOn&&!pickFace)return;
    if(optics.active&&!optics.pending)optics.cancel('已切换工具，未应用的镜头/透视修改已丢弃');
    for(const owner of [sourcePatch,wbPicker,cloneStamp,localMasks,colorPicker,recovery,manual,studio,sky])
      if(owner.workflow.capturing()&&!owner.workflow.busy())owner.workflow.cancel('已切换工具，未提交的手势已取消');
    if(liveGrade.busy)liveGrade.workflow.cancel('已切换画笔工具，未提交调色已取消');
  },[brushOn,pickFace,sourcePatch.workflow,wbPicker.workflow,cloneStamp.workflow,localMasks.workflow,colorPicker.workflow,recovery.workflow,liveGrade.workflow,manual.workflow,studio.workflow,sky.workflow,optics.active,optics.pending,optics.cancel]);
  return {sourcePatch,wbPicker,cloneStamp,localMasks,colorPicker,recovery,liveGrade,manual,studio,optics,sky};
}
