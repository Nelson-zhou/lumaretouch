// AUTHORED / UNRUN. Source-contract fixtures, not executed; no TypeScript or mounted UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./ChinLengthControl.tsx'), model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "chin_length.amount":'), panel.indexOf('case "face_contour.temple":'));
const legacyBranch = panel.slice(panel.indexOf('case "deform.small_chin":'), panel.indexOf('case "deform.big_eye":'));

test('only the exact frozen chin-length leaf routes to the new operation', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/下巴长短"'));
  assert.ok(panel.includes('"PC-32466|脸型/下巴长短": "chin_length.amount"'));
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "chin_length\./g) ?? []).length, 1);
  assert.ok(model.includes("CHIN_LENGTH_OPERATION = 'lnx.chin_length.v1'"));
  assert.ok(model.includes("CHIN_LENGTH_CONTROL_ID = 'LNX-REF-PC-32466-C-44a42baef4'"));
  assert.ok(control.includes('data-control-id={CHIN_LENGTH_CONTROL_ID}'));
  assert.ok(branch.includes('<ChinLengthControl key={leaf.path}'));
});

test('neighboring controls, old small-chin route and every historical preset keep their identities', () => {
  for (const original of ['"PC-32466|脸型/瘦脸": "slim_face.v2"', '"PC-32466|脸型/小脸": "face_size.amount"',
    '"PC-32466|脸型/中庭": "mid_face.amount"', '"PC-32466|脸型/下庭": "lower_face.amount"',
    '"PC-32466|脸型/尖下巴": "chin_shape.v1"', '"PC-32466|脸型/太阳穴": "face_contour.temple"',
    '"PC-32466|脸型/颧骨": "face_contour.cheekbone"', '"PC-32466|脸型/下颌": "face_contour.jaw"',
    '"PC-32466|脸型/收下巴": "deform.small_chin"', '"PC-32466|眉毛": "brow.family"',
    '"PC-32466|鼻子": "nose.family"', '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }']) assert.ok(panel.includes(original));
  assert.ok(legacyBranch.includes('<LegacySmallChinControl key={leaf.path}'));
  assert.ok(legacyBranch.includes('commitDeform({small_chin: value / 100})'));
  assert.ok(legacyBranch.includes('min={0} max={100}'));
  assert.ok(legacyBranch.includes('amounts.small_chin >= 0 && amounts.small_chin <= 1'));
  assert.ok(legacyBranch.includes('amounts.small_chin >= -1 && amounts.small_chin < 0'));
  assert.ok(legacyBranch.includes('已保存的旧版小下巴实际值'));
  assert.ok(legacyBranch.includes('仅归零保存的旧版小下巴'));
  assert.ok(panel.includes('与新版瘦脸或新版下巴长短的非零效果冲突时引擎会拒绝整个请求'));
  assert.ok(control.includes('label="小下巴"'));
  assert.ok(model.includes("parameter_path: '/small_chin'"));
});

test('unmanaged new documents refuse rather than alias an old operation or invent a native path', () => {
  for (const text of ['if (!doc?.people) return <section', '下巴长短暂不可用', '旧效果保留不变']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'runCrop', 'amounts.small_chin']) {
    assert.equal(branch.includes(forbidden), false);
    assert.equal(control.includes(forbidden), false);
  }
  assert.ok(source('../native.ts').includes('chin_length_available?: boolean'));
  assert.ok(source('../native.ts').includes('chin_length_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.chin_length.v1': '下巴长短（唇下局部纵向长度）'"));
});

test('new and managed legacy controls use existing canonical owner and competing-editor fences', () => {
  for (const routed of [branch, legacyBranch]) {
    for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
      'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
      'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(routed.includes(text));
  }
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'dispatch([chinLengthPatch(value)])',
    'dispatch([legacySmallChinPatch(value)])', 'dispatch(replaceLegacySmallChinPatches(value))']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'runPeopleRequest', 'latestIntent']) {
    assert.equal(control.includes(forbidden), false);
  }
});

test('effective readings and both target explicit intents stay distinct from shared write inputs', () => {
  for (const text of ['targetLabel(view)', 'display(reading.value)', 'provenance(view, reading.source)',
    'display(reading.override)', 'access.editValue !== null', 'value={access.editValue * 100}',
    'value={access.legacyEditValue * 100}', 'reading={access.reading.amount}', 'reading={access.reading.legacy}',
    '所选脸的旧版值可能为 0 而共享范围仍有非零显式设置', '不把所选人脸的继承参数复制给其他人物']) assert.ok(control.includes(text));
  for (const text of ["item.overridePresent ? item.override : target?.scope === 'face' ? item.value : null",
    'legacyActive === true || targetLegacyActive === true', 'legacyActive !== false || targetLegacyActive !== false']) assert.ok(model.includes(text));
  for (const forbidden of ['reading.value ?? 0', 'access.editValue ?? 0', 'access.legacyEditValue ?? 0',
    'neutralChinLength()', 'onBlur=', 'Math.abs(reading.legacy', '-reading.legacy']) assert.equal(control.includes(forbidden), false);
});

test('replacement needs a raw blank-start explicit choice and dispatches exactly one two-leaf transaction', () => {
  const replacement = control.slice(control.indexOf('function ReplacementChoice('), control.indexOf('/** Wrap the existing'));
  for (const text of ["useState('')", 'parseChinLengthChoice(text)', 'choice === null', 'onReplace(choice)',
    '不是旧参数的复制、换算或取反', '不点击替换就保留旧效果']) assert.ok(replacement.includes(text));
  for (const forbidden of ['reading.', 'useEffect', 'useLayoutEffect', 'onBlur=', 'commitLegacy', 'chinLengthPatch']) assert.equal(replacement.includes(forbidden), false);
  const action = control.slice(control.indexOf('function replaceLegacy(value:'), control.indexOf('function checkOriginal()'));
  assert.ok(action.includes('current.current.access.replacementDisabled'));
  assert.ok(action.includes('dispatch(replaceLegacySmallChinPatches(value))'));
  assert.equal((action.match(/dispatch\(/g) ?? []).length, 1);
  assert.ok(model.includes('return [legacySmallChinPatch(0), chinLengthPatch(value)]'));
});

test('new reset is separate and cannot silently reset, migrate or restore the old effect', () => {
  const reset = control.slice(control.indexOf('function resetNew()'), control.indexOf('function commitLegacy('));
  assert.ok(reset.includes('current.current.access.resetDisabled'));
  assert.ok(reset.includes('dispatch(chinLengthResetPatches())'));
  for (const forbidden of ['legacy', 'changeDisabled', 'core.available', 'faceOk', 'reading.']) assert.equal(reset.includes(forbidden), false);
  assert.ok(model.includes('return [chinLengthPatch(0)]'));
  for (const text of ['仅归零当前范围的新版下巴长短', '新版归零保留旧版效果', '缺少核心、有效读数或面部分析时仍可归零']) assert.ok(control.includes(text));
});

test('source and owner changes invalidate drafts, stale callbacks and repeated submissions', () => {
  for (const text of ['owner.current.patch !== people.patch || owner.current.check !== people.check',
    'owner.current.generation + 1', 'chinLengthBindingKey(view), owner.current.generation',
    'mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch && current.current.check === people.check',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}', 'key={`${binding}:replacement`}',
    'key={`${binding}:legacy`}', 'key={`${binding}:legacy-choice`}']) assert.ok(control.includes(text));
});

test('uncertain outcomes query original receipts and engine refusals remain unaltered', () => {
  for (const text of ['people.check()', 'if (stillCurrent()) note(String(error))',
    '查询原请求结果（不重发修改）', 'people.state.message', 'refusal.reason', '以下保留引擎原始原因']) assert.ok(control.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('geometry copy separates source anatomy, local map, historical defect and unrun acceptance', () => {
  for (const text of ['正值拉长，负值缩短，0 无效果', '全部 40 个嘴唇顶点', '下巴尖 152',
    '原图或已返回合成图', '不承诺最终叠加结果的嘴唇或上半脸完全不变',
    '邻近颈部、背景与边缘过渡带可能移动', '侧转、倾斜、遮挡、裁切', '历史错误拓扑',
    '54 和 314 并不是一对下颌支撑点', '不是 AI 重建、3D 塑颜', '不是官方标定',
    '不先清旧再试新版', '预览导出一致性与交互验收均未运行（UNRUN）', '面部重塑功能族仍未完整验收']) assert.ok(control.includes(text));
});
