import type {LocalMaskOwner} from '../localMasks/useLocalMaskWorkflow';
import {PromptedModelSetup} from './PromptedModelSetup';
/** Reuses the existing capture, actual prediction, presentation and acceptance owners. */
export function CuratedIdBackgroundSetup({owner,blocked,onStart}:{owner:LocalMaskOwner;blocked:boolean;onStart:()=>void}){
  const disabled=blocked||!owner.context.enabled||owner.context.canStart===false||owner.active||owner.pending;
  const key=owner.context.documentId+':'+owner.context.contextKey;
  const request=owner.state.request;
  const accepted=owner.state.phase==='success'&&!!request&&request.document_id===owner.context.documentId
    &&request.mutation.action==='accept_prompted';
  return <section className="curatedIdBackground" aria-label="精选扩展：证件照主体选择" data-readonly-scopes>
    <h4>精选扩展 · 证件照主体选择</h4>
    <p>安装一次，再用点 / 框生成主体候选；不生成或改写人脸。候选需要你检查并保留，再在下方独立审核主体范围、选择背景并应用。</p>
    <PromptedModelSetup expanded useKey={key} useDisabled={disabled} onUse={()=>{if(disabled)return;onStart();}}/>
    {accepted&&<p role="status">选区提交已获确认。请在下方“独立审核保留范围”选择当前照片的对象，检查边缘后确认；本扩展没有自动审核或应用背景。</p>}
    <small>保留发丝与关联物品仍须人工检查；当前 CPU 准备检查不证明证件照规格合规或最终导出画质。</small>
  </section>;
}
