// AUTHORED / UNRUN. These source assertions and all product imports/build/typechecks are unexecuted.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./BodyFaceMatchControl.tsx');
const model = source('./model.ts'), body = source('../skinColour/bodyReviewModel.ts');
const review = source('../skinColour/SkinBodyPanel.tsx'), disclosure = source('./OwnFaceReferenceDisclosure.tsx');
const route = panel.slice(panel.indexOf('case "body_face_match.amount":'), panel.indexOf('case "skin_colour.temperature":'));

test('exact separate body-to-own-face leaf preserves body/face evenness and legacy routing', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "肤色统一（身体）"'));
  assert.ok(panel.includes('"PC-32465|肤色统一（身体）": "body_face_match.amount"'));
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "body_face_match\./g) ?? []).length, 1);
  assert.ok(route.includes('<BodyFaceMatchControl'));
  for (const text of ["'LNX-REF-PC-32465-C-d8b09012a9'", "'lnx.body_face_match.v1'", "'身体向本人脸部色度匹配（手绘审核）'"]) assert.ok(model.includes(text));
  for (const text of ['"PC-32465|AI肤色统一（身体）": "body_skin_evenness.amount"',
    '"PC-32465|AI肤色统一（脸部）": "skin_evenness.amount"', 'case "body_skin_evenness.amount":',
    'case "skin_colour.temperature":', 'case "skin_finish.whitening":', 'data-legacy-skin-compat="true"']) assert.ok(panel.includes(text));
  for (const forbidden of ['runEnhance', 'runGrade', 'runExposure', 'invoke(', 'setStrength', 'createPeopleWorkflow']) assert.equal(control.includes(forbidden), false);
});

test('canonical owner and target authority gate active changes while exact neutral recovery remains available', () => {
  for (const text of ['body_face_match_available?: boolean', 'body_face_match_reason?: string | null']) assert.ok(source('../native.ts').includes(text));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'props.hairBusy', 'props.whiteBalanceBusy',
    'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending', 'status?.edit_queue?.closed']) assert.ok(route.includes(text));
  for (const text of ['validOwnFaceReference(report.own_face_reference, report.face_ref)', "skinBodyAttached(view, 'body_face_match')",
    'reviewDisabled || !reviewed', 'sourceMatches(view, selected.face_ref, source)', 'source.contributing_targets.every(belongs)',
    "link.state === 'confirmed'", 'link.confirmation_revision <= view.association_revision',
    "view?.editing_target?.scope === 'face' ? reading.value : null", 'view.body_face_match', 'return [bodyFaceMatchPatch(0)]']) assert.ok(model.includes(text));
  for (const text of ['people.patch(patches)', 'owner.current.generation + 1', 'current.current.patch === people.patch',
    'current.current.check === people.check', 'current.current.submitCaptured === people.submitCaptured', 'submitted.current = true',
    'if (!stillCurrent() || submitted.current) return', 'people.check()', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  assert.equal(control.includes('reading.value ?? 0'), false);
  const reset = control.slice(control.indexOf('function reset()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('access.resetDisabled'));
  for (const forbidden of ['reading.value', 'reviewed', 'core.available', 'faceOk']) assert.equal(reset.includes(forbidden), false);
});

test('first use privately stages explicit positive amount and confirms only one exact owned candidate', () => {
  for (const verb of ['reference', 'preview', 'confirm', 'detach']) {
    assert.ok(body.includes(`'body_face_match_${verb}'`));
    assert.ok(source('../people/model.ts').includes(`'body_face_match_${verb}'`));
    assert.ok(source('../../src-tauri/src/people_api.rs').includes(`"body_face_match_${verb}"`));
  }
  for (const text of ['family="body_face_match"', 'reviewBinding={binding}', 'reviewCanSubmit={!access.reviewDisabled}',
    'detachNeutral={reading.value === 0}']) assert.ok(control.includes(text));
  for (const text of ['stagedBody = evenness || faceMatch', 'stagedBody ? {review, amount} : {review}',
    'parseBodyReviewAmount(amountText)', 'preview.amount === amount', 'preview_id: preview.preview_id, reviewed: true',
    '(!stagedBody || detachNeutral)', '不写入分组、关联人物或全部默认', '确认审核前不写入效果',
    '不会偷偷清除或恢复共享范围强度', 'skinBodyRequestFits(command)', 'people.submitCaptured(command)',
    'liveDraft.current !== draftSnapshot', 'referenceMatches(reference, view, family)']) assert.ok(review.includes(text));
  assert.ok(body.includes('identity.family === undefined && identity.operation_id === undefined'));
  assert.ok(body.includes('preview.reference_source_stage === reference.reference_source_stage'));
  assert.ok(body.includes('bodyReviewKey(preview.own_face_reference) === bodyReviewKey(reference.own_face_reference)'));
  assert.ok(body.includes('bodyReviewKey(preview.reference_support) === bodyReviewKey(reference.reference_support)'));
});

test('actual sampled own-face reference is loaded and accepted separately with no arbitrary face selector', () => {
  for (const text of ['<OwnFaceReferenceDisclosure', 'reference.reference_overlay', 'reference.reference_source_stage',
    'referenceReady = !faceMatch || (referenceLoaded && referenceAccepted)', '&& !referenceReady) return',
    'comparisonLoaded', 'draftMatches', 'naturalWidth === image.width', 'naturalHeight === image.height',
    'reviewSession.current++', 'reviewSession.current === imageSession', 'currentPreview.current !== preview.preview_id',
    'liveCanvasKey.current === canvasKey', 'receipt.result.payload_released']) assert.ok(review.includes(text));
  for (const text of ['naturalWidth === image.displayWidth', 'naturalHeight === image.displayHeight', 'busy || !loaded',
    'reference_samples', 'protected_face_boxes', '洋红色', '来源阶段审核网格', 'image.decodedWidth', 'image.decodedHeight',
    '这是审核代理图，不是 100% 或全分辨率测量图', '全来源数值参考会另行重算',
    '不是后续修饰后的脸', '不匹配亮度，也不复制脸部 RGB', "stage === 'verified-repair-base'"]) assert.ok(disclosure.includes(text));
  assert.equal(disclosure.includes('<select'), false);
  assert.equal(control.includes('donor_face'), false);
});

test('honest scope exposes partial manual assistance, actual stage luminance and quality still UNRUN', () => {
  for (const text of ['官方条目“肤色统一（身体）”', '当前仅部分实现', '肖像效果之前的冻结来源阶段',
    '包含已验证的现有修复', '不是学习型 AI', '不代表官方完整效果或专有算法等效',
    '保留实际输入的线性亮度', '不匹配脸部亮度、不复制脸部 RGB', '不保证身体等同于后续修饰后的脸',
    '不识别妆容，不分离物理光照与皮肤材质', '任一实际启用人物缺少本功能有效审核时，引擎必须拒绝',
    '非零强度不保证可见变化', '仅支持 RGB SDR', '验收均未运行（UNRUN）']) assert.ok(control.includes(text));
});
