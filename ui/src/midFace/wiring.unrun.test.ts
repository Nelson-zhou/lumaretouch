// AUTHORED / UNRUN. Source-contract fixtures only; imports, execution, compilation and UI acceptance were NOT performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./MidFaceControl.tsx');
const model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "mid_face.amount":'), panel.indexOf('case "lower_face.amount":'));

test('only the exact mid-face handbook leaf routes here; all neighboring routes and historical presets remain', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/中庭"'));
  assert.ok(panel.includes('"PC-32466|脸型/中庭": "mid_face.amount"'));
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "mid_face\./g) ?? []).length, 1);
  assert.ok(branch.includes('<MidFaceControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={MID_FACE_CONTROL_ID}'));
  assert.ok(model.includes("MID_FACE_OPERATION = 'lnx.mid_face.v1'"));
  assert.ok(model.includes("MID_FACE_CONTROL_ID = 'LNX-REF-PC-32466-C-ea67c9d99f'"));
  for (const original of ['"PC-32466|脸型/瘦脸": "slim_face.v2"', '"PC-32466|脸型/小脸": "face_size.amount"',
    '"PC-32466|脸型/下庭": "lower_face.amount"',
    '"PC-32466|脸型/太阳穴": "face_contour.temple"', '"PC-32466|脸型/颧骨": "face_contour.cheekbone"',
    '"PC-32466|脸型/下颌": "face_contour.jaw"', '"PC-32466|脸型/收下巴": "deform.small_chin"',
    '"PC-32466|眉毛": "brow.family"', '"PC-32466|鼻子": "nose.family"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }']) assert.ok(panel.includes(original));
});

test('unmanaged documents explicitly refuse, with no lower-face/chin/short-face/whole-image or separate native substitute', () => {
  for (const text of ['if (!doc?.people) return <section', '中庭暂不可用', '不会改用下庭、小脸、收下巴、下巴长短或短脸替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'resize(', 'runCrop', 'setStrength', 'amounts.small_chin']) {
    assert.equal(branch.includes(forbidden), false);
    assert.equal(control.includes(forbidden), false);
  }
  assert.equal(branch.includes('<LowerFaceControl'), false);
  assert.equal(control.includes('../lowerFace/'), false);
  assert.equal(model.includes("'lnx.lower_face.v1'"), false);
});

test('dedicated capability and every competing-owner fence feed the existing single people owner', () => {
  assert.ok(source('../native.ts').includes('mid_face_available?: boolean'));
  assert.ok(source('../native.ts').includes('mid_face_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.mid_face.v1': '中庭（局部纵向长度）'"));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'dispatch([midFacePatch(value)])',
    'dispatch(midFaceResetPatches())']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'latestIntent', 'runPeopleRequest']) {
    assert.equal(control.includes(forbidden), false);
  }
});

test('selected actual values and shared explicit/blank choices never collapse into a borrowed or neutral baseline', () => {
  for (const text of ["const source = resolved.operations[MID_FACE_OPERATION]?.['/amount']",
    "target?.scope === 'face' ? reading.value : null", 'reading.overridePresent ? reading.override']) assert.ok(model.includes(text));
  for (const text of ['targetLabel(view)', 'display(reading.value)', 'provenance(view, reading.source)',
    'display(reading.override)', 'access.editValue !== null', 'value={access.editValue * 100}',
    "useState('')", 'parseMidFaceChoice(text)', 'choice === null', 'onChoose(choice)',
    'min={-100} max={100}', 'onChange={value => commit(value / 100)}',
    '不把所选人脸的继承参数复制给其他人物']) assert.ok(control.includes(text));
  for (const forbidden of ['reading.value ?? 0', 'access.editValue ?? 0', 'neutralMidFace()', 'onBlur=',
    'linked', 'setLinked', 'left:', 'right:']) assert.equal(control.includes(forbidden), false);
});

test('late callbacks, repeated clicks and uncertain results cannot retarget or duplicate writes', () => {
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

test('neutral action is separate from unreadable amount inputs and keeps ownership without anatomy/native gates', () => {
  const reset = control.slice(control.indexOf('function resetAmount()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(midFaceResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'editValue']) assert.equal(reset.includes(forbidden), false);
  assert.ok(control.indexOf('disabled={access.resetDisabled} onClick={resetAmount}') > control.indexOf('<AmountChoice key='));
  assert.ok(model.includes('return [midFacePatch(0)]'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
  assert.ok(control.includes('归零写入中性覆盖，不恢复继承'));
});

test('measured eye boundary, cheek AND nose ramp, lower-face plateau and composition limits are explicit', () => {
  for (const text of ['正值拉长，负值缩短', '不是下庭、整脸大小、收下巴、仅下巴长短或以耳朵为依据的短脸调整',
    '当前有效来源图像（原图或已返回合成图）', '真实 478 点分析', '实测代理点', '不是临床中庭测量或临床解剖标志',
    '不能单凭关键点确认遮挡部位是否可见', '上方固定边界取在全部保留的眼部轮廓下方', '头部局部坐标系',
    '脸颊与鼻部带的纵向位移从眼下固定边界起平滑、非均匀地增加', '至鼻基底代理点进入平台',
    '下方包括嘴唇与下巴的区域等量平移', '再向颈部与背景平滑衰减',
    '鼻部也参与形变，不承诺鼻形不变', '不是仅对苹果肌进行真实分割', '不是整片中庭均匀缩放',
    '只有本次新增映射保持局部横向坐标及眼下固定边界以上半平面（含全部保留眼部轮廓）不变',
    '先前编辑可能已把点移入过渡带', '横向核心区', '邻近颈部、背景过渡带也会移动',
    '不是 AI 重建、3D 塑颜或新增分割', '每个目标必须使用自己的真实分析',
    '已有几何调整与当前有效来源由引擎统一检查和组合', '界面不绕过手动液化等兼容性限制',
    '核心就绪不代表此脸或当前组合可用', '以下保留引擎原始原因', 'view?.refusals?.map', '{refusal.reason}',
    '显示 -100 至 100 对应内部 -1 至 1', '不是手册规定', '1 + 0.08 × amount', '0.92 到 1.08',
    '原始眼下固定边界至鼻基底代理端点间距的局部比例', '不是所有中庭位置的缩放比例',
    '不是实拍效果读数', '不是官方质量指标', '增益、固定边界与过渡形状均为本产品局部策略，不是官方标定',
    '均未运行（UNRUN）', '面部重塑功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['mid_face_applied', 'mid_face_facts', 'support_px', 'composition_available',
    'manual_liquify_available', 'skipCompatibility', 'lower_face_available', 'face_size_available', 'face_contour_available']) {
    assert.equal(model.includes(invented), false);
    assert.equal(control.includes(invented), false);
  }
});
