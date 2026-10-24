// AUTHORED / UNRUN. Source-contract fixtures only; no imports, execution, compilation or UI acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./FaceSizeControl.tsx');
const model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "face_size.amount":'), panel.indexOf('case "face_contour.temple":'));

test('only the exact small-face handbook leaf routes to the distinct operation; existing routes and presets remain', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/小脸"'));
  assert.ok(panel.includes('"PC-32466|脸型/小脸": "face_size.amount"'));
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "face_size\./g) ?? []).length, 1);
  assert.ok(branch.includes('<FaceSizeControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={FACE_SIZE_CONTROL_ID}'));
  assert.ok(model.includes("FACE_SIZE_OPERATION = 'lnx.face_size.v1'"));
  assert.ok(model.includes("FACE_SIZE_CONTROL_ID = 'LNX-REF-PC-32466-C-728fc62cdd'"));
  for (const original of ['"PC-32466|脸型/瘦脸": "slim_face.v2"',
    '"PC-32466|脸型/太阳穴": "face_contour.temple"', '"PC-32466|脸型/颧骨": "face_contour.cheekbone"',
    '"PC-32466|脸型/下颌": "face_contour.jaw"', '"PC-32466|脸型/收下巴": "deform.small_chin"',
    '"PC-32466|眉毛": "brow.family"', '"PC-32466|鼻子": "nose.family"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }']) assert.ok(panel.includes(original));
});

test('unmanaged documents are explicitly unavailable, with no legacy, image-resize or separate native fallback', () => {
  for (const text of ['if (!doc?.people) return <section', '小脸暂不可用', '不会改用整张图像缩放、旧版瘦脸或五官大小替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'resize(', 'runCrop', 'setStrength', 'amounts.slim_face']) {
    assert.equal(branch.includes(forbidden), false);
    assert.equal(control.includes(forbidden), false);
  }
});

test('dedicated capability and every competing-owner fence feed the existing people owner', () => {
  assert.ok(source('../native.ts').includes('face_size_available?: boolean'));
  assert.ok(source('../native.ts').includes('face_size_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.face_size.v1': '小脸（局部整脸整体大小）'"));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'dispatch([faceSizePatch(value)])',
    'dispatch(faceSizeResetPatches())']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'latestIntent', 'runPeopleRequest']) {
    assert.equal(control.includes(forbidden), false);
  }
});

test('selected effective source and shared target values are displayed separately with no placeholder or borrowed baseline', () => {
  for (const text of ['const source = resolved.operations[FACE_SIZE_OPERATION]?.[\'/amount\']',
    "target?.scope === 'face' ? reading.value : null", 'reading.overridePresent ? reading.override']) assert.ok(model.includes(text));
  for (const text of ['targetLabel(view)', 'display(reading.value)', 'provenance(view, reading.source)',
    'display(reading.override)', 'access.editValue !== null', 'value={access.editValue * 100}',
    'useState(\'\')', 'parseFaceSizeChoice(text)', 'choice === null', 'onChoose(choice)',
    'min={-100} max={100}', 'onChange={value => commit(value / 100)}',
    '不把所选人脸的继承参数复制给其他人物']) assert.ok(control.includes(text));
  for (const forbidden of ['reading.value ?? 0', 'access.editValue ?? 0', 'neutralFaceSize()', 'onBlur=',
    'linked', 'setLinked', 'left:', 'right:']) assert.equal(control.includes(forbidden), false);
});

test('late callbacks, repeated clicks and uncertain outcomes cannot silently retarget or resend a mutation', () => {
  for (const text of ['mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}',
    'current.current.access.resetDisabled : current.current.access.changeDisabled',
    'people.check()', 'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('dedicated neutral action is outside the readable amount control and independent of core/anatomy', () => {
  const reset = control.slice(control.indexOf('function resetAmount()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(faceSizeResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'editValue']) assert.equal(reset.includes(forbidden), false);
  assert.ok(control.indexOf('disabled={access.resetDisabled} onClick={resetAmount}') > control.indexOf('<AmountChoice key='));
  assert.ok(model.includes('return [faceSizePatch(0)]'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
  assert.ok(control.includes('归零写入中性覆盖，不恢复继承'));
});

test('whole-face semantics, local range and quality limits are visible without invented composition availability', () => {
  for (const text of ['正值整体缩小，负值整体放大', '不是只收窄轮廓', '不是分别调整眼、鼻、嘴',
    '当前有效来源图像（原图或已返回合成图）', '核心区内整张脸与内部五官按同一比例缩放',
    '附近背景、头发和颈部过渡带也会移动', '只支持正脸与轻度偏转',
    '不是 AI 重建、3D 塑颜或脸部/身体分割', '每个目标必须使用自己的真实分析',
    '已有几何调整与当前有效来源由引擎统一检查和组合', '界面不绕过手动液化等兼容性限制',
    '核心就绪不代表此脸或当前组合可用', '以下保留引擎原始原因', 'view?.refusals?.map', '{refusal.reason}',
    '显示 -100 至 100 对应内部 -1 至 1', '不是手册规定', '1 − 0.06 × amount', '1.06 到 0.94',
    '不是官方质量指标', '均未运行（UNRUN）', '面部重塑功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['face_size_applied', 'face_size_facts', 'support_px', 'composition_available',
    'manual_liquify_available', 'skipCompatibility', 'face_contour_available', 'skin_texture_available']) {
    assert.equal(model.includes(invented), false);
    assert.equal(control.includes(invented), false);
  }
});
