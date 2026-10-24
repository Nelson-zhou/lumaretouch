// AUTHORED / UNRUN. Static-source fixtures only; no imports, UI, tests, build or typecheck performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./BodySkinEvennessControl.tsx');
const model = source('./model.ts'), review = source('../skinColour/SkinBodyPanel.tsx');
const body = source('../skinColour/bodyReviewModel.ts');
const route = panel.slice(panel.indexOf('case "body_skin_evenness.amount":'), panel.indexOf('case "skin_colour.temperature":'));

test('only the exact body leaf has its independent partial control and operation', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "AI肤色统一（身体）"'));
  assert.ok(panel.includes('"PC-32465|AI肤色统一（身体）": "body_skin_evenness.amount"'));
  assert.equal((panel.match(/"PC-32465\|[^"\n]+": "body_skin_evenness\./g) ?? []).length, 1);
  assert.ok(route.includes('<BodySkinEvennessControl'));
  assert.ok(control.includes('data-control-id={BODY_SKIN_EVENNESS_CONTROL_ID}'));
  assert.ok(control.includes('aria-label={BODY_SKIN_EVENNESS_LABEL}'));
  assert.ok(model.includes("'LNX-REF-PC-32465-C-d5ac2d4606'"));
  assert.ok(model.includes("'lnx.body_skin_evenness.v1'"));
  assert.ok(model.includes("'身体色度均匀（手绘审核、自身参考）'"));
  assert.ok(source('../people/model.ts').includes("'lnx.body_skin_evenness.v1': '身体色度均匀（手绘审核、自身参考）'"));
  for (const forbidden of ['d8b09012a9', 'skin.broad', 'broad_gain', 'detail_gain', 'setStrength', 'runEnhance',
    'runGrade', 'runExposure', 'invoke(', 'createPeopleWorkflow']) {
    assert.equal(control.includes(forbidden), false); assert.equal(model.includes(forbidden), false);
  }
});

test('face-evenness, legacy and neighbouring skin routes remain distinct', () => {
  for (const existing of ['"PC-32465|AI肤色统一（脸部）": "skin_evenness.amount"',
    '"PC-32465|肤色色温": "skin_colour.temperature"', '"PC-32465|肤色色调": "skin_colour.tint"',
    '"PC-32465|肤色美白": "skin_finish.whitening"', '"PC-32465|皮肤红润": "skin_finish.rosiness"',
    '"PC-32465|皮肤质感/光泽度": "skin_gloss.amount"', '"PC-32465|皮肤质感/纹理度": "skin_texture.texture"',
    '"PC-32465|皮肤质感/清晰度": "skin_texture.clarity"', 'data-legacy-skin-compat="true"',
    'onChange={value => commitSkin({ broad: value })}', 'onReset={() => commitSkin({ broad: 0 })}']) assert.ok(panel.includes(existing));
  assert.ok(review.includes('`${family}:${skinColourBindingKey(view)}`'));
  assert.ok(review.includes('previewMatches(payload, reference, request.review, family)'));
  assert.ok(review.includes('evenness ? {review, amount} : {review}'));
  assert.ok(body.includes('identity.family === undefined && identity.operation_id === undefined'));
  assert.ok(body.includes("skin_finish: {operation: 'lnx.skin_finish.v1', report: 'skin_finish_body'"));
});

test('own readiness, selected authority, shared intent and current owner fences remain separate', () => {
  for (const text of ['body_skin_evenness_available?: boolean', 'body_skin_evenness_reason?: string | null']) assert.ok(source('../native.ts').includes(text));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}', 'Slider={Slider}']) assert.ok(route.includes(text));
  for (const text of ['sourceMatches(view, selected.face_ref, source)', 'source.contributing_targets.every(belongs)',
    "link.state === 'confirmed'", 'link.confirmation_revision <= view.association_revision',
    "view?.editing_target?.scope === 'face' ? reading.value : null", 'reading.overridePresent',
    'view.groups, view.persons, view.links', 'view.body_skin_evenness', 'reviewDisabled || !reviewed']) assert.ok(model.includes(text));
  for (const text of ['targetLabel(view)', 'sourceLabel(source)', 'display(reading.value)', 'value={access.editValue * 100}',
    'onChange={value => commit(value / 100)}', "useState('')", 'parseBodySkinEvennessChoice(text)',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}', '留空不等于 0', '不把某一人物的继承值、身体范围或参考色复制']) assert.ok(control.includes(text));
  assert.equal(control.includes('reading.value ?? 0'), false);
  for (const alias of ['skin_colour_available', 'skin_finish_available', 'skin_semantics_available', 'skin_gloss_available']) assert.equal(model.includes(alias), false);
});

test('canonical dispatch guards owner replacement, stale callbacks and duplicate submissions', () => {
  for (const text of ['people.patch(patches)', 'dispatch([bodySkinEvennessPatch(value)])', 'dispatch(bodySkinEvennessResetPatches())',
    'owner.current.patch !== people.patch', 'owner.current.check !== people.check', 'owner.current.submitCaptured !== people.submitCaptured',
    'owner.current.generation + 1', 'mounted.current && current.current.binding === binding',
    'current.current.patch === people.patch', 'current.current.check === people.check', 'current.current.submitCaptured === people.submitCaptured',
    'mounted.current = false', 'if (!stillCurrent() || submitted.current) return', 'submitted.current = true',
    'if (!people.state.pending && !people.state.uncertain) submitted.current = false',
    'current.current.access.resetDisabled : current.current.access.changeDisabled', 'people.check()',
    '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  assert.equal(control.includes('people.submitCaptured('), false);
  for (const text of ['people.submitCaptured(command)', 'skinBodyRequestFits(command)', 'request.context !== latest.current',
    'liveDraft.current !== draftSnapshot', 'referenceMatches(reference, view, family)', 'liveCanvasKey.current === canvasKey',
    'if (expected.current || live.current.context !== context', 'receipt.result.payload_released', '已发请求仍待确认']) assert.ok(review.includes(text));
});

test('independent body review stages explicit amount and confirms one atomic candidate only after three real images', () => {
  for (const text of ['family="body_skin_evenness"', 'reviewBinding={binding}', 'reviewCanSubmit={!access.reviewDisabled}',
    'detachNeutral={reading.value === 0}']) assert.ok(control.includes(text));
  for (const verb of ['reference', 'preview', 'confirm', 'detach']) {
    const action = `body_skin_evenness_${verb}`;
    assert.ok(body.includes(`'${action}'`)); assert.ok(source('../people/model.ts').includes(`'${action}'`));
    assert.ok(source('../../src-tauri/src/people_api.rs').includes(`"${action}"`));
  }
  for (const text of ['parseBodyReviewAmount(amountText)', "setAmountText('')", 'amount: candidateAmount',
    'previewMatches(payload, reference, request.review, family, request.amount)', 'preview.amount === amount',
    'evenness ? {review, amount} : {review}', '本次候选身体强度', '确认审核前不写入效果',
    'preview_id: preview.preview_id, reviewed: true', 'comparisonLoaded', 'draftMatches',
    'naturalWidth === image.width', 'naturalHeight === image.height', '独立接受{operationLabel}',
    '确认此身体范围，并将此人物独立强度设为', '不写入分组、关联人物或全部默认',
    '不复制色温、美白红润或脸部蒙版', '先在全身塑形中完成身体分析与人物关联']) assert.ok(review.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ['skinBodyActionFamily(command.action)', 'skinBodyFamilyMatches(result.payload, bodyFamily)',
    'lastBodyResult: skinBodyReceiptCurrent(command, result, current)', 'result.outcome_unknown']) assert.ok(workflow.includes(text));
});

test('neutral recovery stays independent of core/support and detach requires authoritative neutral', () => {
  const reset = control.slice(control.indexOf('function reset()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('current.current.access.resetDisabled'));
  for (const forbidden of ['changeDisabled', 'reading.value', 'reviewed', 'core.available', 'faceOk']) assert.equal(reset.includes(forbidden), false);
  for (const text of ['return [bodySkinEvennessPatch(0)]', "parameter_path: '/amount', unset: false, value"]) assert.ok(model.includes(text));
  assert.ok(review.includes('(!evenness || detachNeutral)'));
  assert.ok(review.includes('须先归零'));
  assert.ok(review.includes('不会偷偷清除或恢复共享范围强度'));
  assert.ok(control.includes('不恢复继承，不移除审核范围，不清除其他范围或其他效果'));
  assert.ok(control.includes('缺少核心、有效读数、身体审核或面部分析时仍可归零'));
});

test('manual-assisted own-body limits and current-stage luminance guarantee are visible and UNRUN', () => {
  for (const text of ['官方条目“AI肤色统一（身体）”针对身体各部位肤色不均', '当前仅部分实现',
    '当前有效来源图像（原图或已返回合成图）', '同一人物独立手绘审核的身体皮肤低频色度为自身参考',
    '不是学习型 AI 或自动身体皮肤实例识别', '不代表官方完整效果或专有算法等效',
    '仅在本项处理阶段保留输入的线性亮度', '不承诺其他效果叠加后的最终亮度不变',
    '不是提亮、美白、大范围模糊或全图染色', '不识别妆容，不分离物理光照与皮肤材质',
    '不会自动判断这些差异是否应当去除', '不会补全衣物下或被遮挡的皮肤', '不是脸身肤色匹配',
    '任一实际启用人物缺少本功能有效审核时，引擎必须拒绝', '不能靠所选人物的审核替其授权',
    '非零强度不保证可见变化', '仅支持 RGB SDR，不宣称 HDR 支持', '不是官方标定',
    '验收均未运行（UNRUN）', '皮肤功能族仍未完整验收']) assert.ok(control.includes(text));
});
