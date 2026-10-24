// AUTHORED / UNRUN. These are source-inspection fixtures, not evidence of runtime success.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const control = source('./CollarboneControl.tsx'), editor = source('./ClavicleSourceEditor.tsx');
const model = source('./model.ts'), panel = source('../skinColour/SkinBodyPanel.tsx'), body = source('../skinColour/bodyReviewModel.ts');
test('official leaf has independent partial operation, capability and exact native action admission', () => {
  const retouch = source('../components/RetouchPanel.tsx');
  for (const text of ['"PC-32465|锁骨增强": "collarbone.amount"', 'case "collarbone.amount":', '<CollarboneControl']) assert.ok(retouch.includes(text));
  for (const text of ['lnx.collarbone.v1', 'LNX-REF-PC-32465-C-abf0a5c8c9', '锁骨现有明暗增强（手绘审核）']) assert.ok(model.includes(text));
  for (const text of ['collarbone_available?: boolean', 'collarbone_reason?: string | null']) assert.ok(source('../native.ts').includes(text));
  for (const suffix of ['reference', 'preview', 'confirm', 'detach']) {
    const action = 'collarbone_' + suffix; assert.ok(body.includes(action)); assert.ok(source('../people/model.ts').includes(action));
    assert.ok(source('../../src-tauri/src/people_api.rs').includes(`"${action}"`));
  }
});
test('source canvas captures all points explicitly with no arbitrary JSON or anatomical templates', () => {
  for (const text of ['matchesSource(image', 'naturalWidth === image.displayWidth', 'naturalHeight === image.displayHeight',
    'bodyMaskPoint(event.clientX', 'onPointerDown={place}', 'imageCurrent()', 'live.current.draftKey === draftKey',
    'live.current.interactionKey === interactionKey', 'mounted.current = false', 'points.length >= 8',
    '点击添加控制点', '移动选中控制点', '删除所选点', '清空本侧曲线', '清空全部曲线', '来源图像素，4 至 256',
    '图像左侧', '图像右侧', 'category', 'eligibility_confirmed', 'visible_anatomy_confirmed',
    '没有预置点、自动检测或另一侧补全', '锁骨曲线来源像素半宽']) assert.ok(editor.includes(text));
  for (const forbidden of ['<textarea', 'JSON.parse', 'defaultPoints', 'autoDetect', 'inferGender', 'invoke(']) assert.equal(editor.includes(forbidden), false);
  assert.ok(source('./clavicleReview.ts').includes("category: ''")); assert.ok(source('./clavicleReview.ts').includes('curves: []'));
});
test('independent mask and trace draft share current-source fences and invalidate old image review', () => {
  for (const text of ['<SkinBodySourceEditor', '<ClavicleSourceEditor', 'review.clavicle = checkClavicleReview',
    'clavicleReviewError(clavicle, reference.source)', 'setClavicle(emptyClavicleDraft())', 'setClavicleLoaded(false)',
    'clavicle, clavicleLoaded', 'liveDraft.current !== draftSnapshot', 'liveCanvasKey.current !== canvasKey',
    '(!collarbone || Object.values(flags).every(Boolean))', 'bodyReviewKey(preview.review)',
    'previewMatches(payload, reference, request.review, family, request.amount)', 'comparisonLoaded',
    'runtime_quality_accepted: false']) assert.ok((panel + body).includes(text));
  assert.ok(body.includes("family === 'collarbone' ? clavicleReviewError(review.clavicle, reference.source) === null"));
  assert.ok(body.includes('review.clavicle === undefined && preview.review?.clavicle === undefined'));
});
test('private positive candidate and final three-image consent still use canonical receipts, not direct native calls', () => {
  for (const text of ['parseBodyReviewAmount(amountText)', 'stagedBody ? {review, amount} : {review}',
    'skinBodyRequestFits(command)', 'people.submitCaptured(command)', 'preview_id: preview.preview_id, reviewed: true',
    'receipt.result.payload_released', 'imageCurrent()', 'currentPreview.current !== preview.preview_id']) assert.ok(panel.includes(text));
  for (const text of ['people.patch(patches)', 'owner.current.generation + 1', 'current.current.patch === people.patch',
    'current.current.check === people.check', 'current.current.submitCaptured === people.submitCaptured',
    'submitted.current = true', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  for (const forbidden of ['invoke(', 'createPeopleWorkflow', 'runEnhance', 'setStrength']) assert.equal(control.includes(forbidden), false);
});
test('neutral reset remains current-owner-only and explicit conflicting labels never get silently edited', () => {
  for (const text of ['clavicleApplicabilityConflict(selected?.labels)', '!!applicabilityReason || resetDisabled',
    'return [collarbonePatch(0)]', "parameter_path: '/amount', unset: false, value"]) assert.ok(model.includes(text));
  assert.ok(control.includes('detachNeutral={reading.value === 0}')); assert.ok(panel.includes('action !== actions.detach && applicabilityReason'));
  assert.equal(editor.includes('face_status'), false); assert.equal(control.includes('face_status'), false);
});
test('truthful partial and unrun disclosure does not call a body-mask overlay a clavicle field map', () => {
  for (const text of ['当前仅部分实现', '不是 AI 3D 重建', '自动锁骨检测', '系统不会从外貌推断性别或年龄',
    '共享范围只共享强度', '不把某一人物的继承值、身体范围、类别确认或锁骨曲线复制',
    '不恢复继承，不移除审核范围，不清除其他范围或其他效果', '非零强度不保证可见变化', '验收均未运行（UNRUN）']) assert.ok(control.includes(text));
  assert.ok(panel.includes('不显示最终锁骨明暗采样区或强度场'));
});
