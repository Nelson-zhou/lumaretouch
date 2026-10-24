// AUTHORED / UNRUN. Source-contract fixtures only; no import, execution, compilation or UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./FaceContourControl.tsx');
const model = source('./model.ts');

test('only exact temple, cheekbone and jaw leaves are routed without aliasing old slim-face or chin', () => {
  for (const [path, key] of [['脸型/太阳穴', 'temple'], ['脸型/颧骨', 'cheekbone'], ['脸型/下颌', 'jaw']]) {
    assert.ok(source('../spec/refine.json').includes(`"path": "${path}"`));
    assert.ok(panel.includes(`"PC-32466|${path}": "face_contour.${key}"`));
    assert.ok(panel.includes(`case "face_contour.${key}":`));
  }
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "face_contour\./g) ?? []).length, 3);
  assert.ok(panel.includes('<FaceContourControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={FACE_CONTOUR_CONTROL_IDS[control]}'));
  for (const existing of ['"PC-32466|脸型/瘦脸": "deform.slim_face"', '"PC-32466|脸型/收下巴": "deform.small_chin"',
    '"PC-32466|眉毛": "brow.family"', '"PC-32466|鼻子": "nose.family"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"']) assert.ok(panel.includes(existing));
});

test('generic owner submits one numeric group, a flag-only toggle and atomic pair/family recovery', () => {
  for (const text of ['people.patch(faceContourAdjustPatches(control, side, value, linked))',
    'people.patch([faceContourLinkPatch(control, linked)])', 'people.patch(faceContourResetPatches(control))',
    'people.patch(faceContourResetPatches())', 'reading.linked.overridePresent', 'access.writeLinked',
    'targetLabel(view)', 'sourceLabel(item.source)', 'item.value !== null', 'min={-100} max={100}',
    'onChange={value => commit(side, value / 100)}', 'onClick={() => setLinked(true)}', 'onClick={() => setLinked(false)}',
    'onClick={resetControl}', 'onClick={resetAll}', 'current.current.access.resetDisabled : current.current.access.changeDisabled',
    'const linked = current.current.access.writeLinked', 'if (linked === null) return']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 4);
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'createPeopleWorkflow', 'people.submit(',
    'people.submitCaptured(', 'runBrow', 'latestIntent', 'neutralFaceContour()']) assert.equal(control.includes(forbidden), false);
  assert.ok(model.includes('const source = resolved.operations[FACE_CONTOUR_OPERATION]?.[path]'));
  assert.ok(source('../people/model.ts').includes("'lnx.face_contour.v1': '太阳穴、颧骨与下颌（可见二维轮廓）'"));
});

test('dedicated readiness and all existing competing-owner fences apply to all three leaves', () => {
  assert.ok(source('../native.ts').includes('face_contour_available?: boolean'));
  assert.ok(source('../native.ts').includes('face_contour_reason?: string | null'));
  const branch = panel.slice(panel.indexOf('case "face_contour.temple":'), panel.indexOf('case "deform.slim_face":'));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim', 'props.hairBusy',
    'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight', 'status?.edit_queue?.pending',
    'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const borrowed of ['skin_texture_available', 'brow_shape_protocol', 'nose_shape_protocol', 'mouth_shape_protocol']) {
    assert.equal(model.includes(borrowed), false);
  }
});

test('late events and uncertain outcomes cannot silently retarget or resend a mutation', () => {
  for (const text of ['mounted.current && current.current.binding === binding && current.current.control === control',
    'mounted.current = false', 'key={`${binding}:${control}:${side}`}', 'people.check()',
    'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  for (const name of ['setLinked', 'resetControl', 'resetAll']) {
    const start = control.indexOf(`function ${name}(`), end = control.indexOf('\n  function ', start + 1);
    assert.ok(control.slice(start, end).includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  }
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('neutral buttons do not require readable sliders, link choice, core or anatomy', () => {
  const slidersEnd = control.indexOf('    })}');
  assert.ok(control.indexOf('onClick={resetControl}') > slidersEnd);
  assert.ok(control.indexOf('onClick={resetAll}') > slidersEnd);
  const resetFunctions = control.slice(control.indexOf('function resetControl()'), control.indexOf('function checkOriginal()'));
  for (const forbidden of ['changeDisabled', 'writeLinked', 'core.available', 'faceOk', 'reading.']) assert.equal(resetFunctions.includes(forbidden), false);
  assert.ok(model.includes("FACE_CONTOUR_SIDES.map(side => faceContourAmountPatch(item, side, 0))"));
});

test('source, directions, subject sides, inherited links and measured 2D limitations stay visible', () => {
  for (const text of ['当前有效来源图像（原图或已返回合成图）', '负值向外扩展，正值向内收窄',
    '负值向内收窄，正值向外扩展', '人物自身解剖侧', '不是观看者或画面左右',
    '人物自身左侧', '人物自身右侧', '仅支持正脸与轻度偏转', '不补造隐藏部位',
    '每个目标必须使用自己的真实分析与可见轮廓证据', '切换联动只改变联动标记',
    '不复制、平均或重置两侧数值', '联动后下一次数值修改才会在同一请求中写入左右两侧',
    '共享范围没有显式联动设置时，必须先选择', '不会把继承的联动设置变为显式值',
    '缺少核心、有效读数或面部分析时仍可归零', '不恢复数值继承',
    '不是旧瘦脸别名', '不是 AI 重建、3D 塑颜或骨骼矫正', '轮廓外的邻近背景过渡带',
    '不能保证背景完全不动', '截断或邻人冲突时应拒绝', '显示 -100 至 100 对应内部 -1 至 1',
    '不是手册规定', '核心就绪不代表此脸或每一侧可用', '验收尚未运行', '功能族仍未完整验收']) assert.ok(control.includes(text));
  assert.ok(control.includes('view?.refusals?.map'));
  assert.ok(control.includes('{refusal.reason}'));
  assert.ok(control.includes('以下保留引擎原始原因'));
  for (const inventedFact of ['support_px', 'side_available', 'side_applied', 'contour_facts']) assert.equal(control.includes(inventedFact), false);
});
