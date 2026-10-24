// AUTHORED / UNRUN. Source-contract fixtures only; imports, execution, compilation and mounted UI acceptance were NOT performed.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./PhiltrumControl.tsx'), model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "philtrum.amount":'), panel.indexOf('case "face_contour.temple":'));

test('only the exact philtrum handbook leaf routes to the distinct philtrum operation', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/人中"'));
  assert.ok(panel.includes('"PC-32466|脸型/人中": "philtrum.amount"'));
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "philtrum\./g) ?? []).length, 1);
  assert.ok(branch.includes('<PhiltrumControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={PHILTRUM_CONTROL_ID}'));
  assert.ok(model.includes("PHILTRUM_OPERATION = 'lnx.philtrum.v1'"));
  assert.ok(model.includes("PHILTRUM_CONTROL_ID = 'LNX-REF-PC-32466-C-2605502c27'"));
});

test('all neighboring routes, historical presets and the previous explicit chin replacement remain intact', () => {
  for (const original of ['"PC-32466|脸型/瘦脸": "slim_face.v2"', '"PC-32466|脸型/小脸": "face_size.amount"',
    '"PC-32466|脸型/中庭": "mid_face.amount"', '"PC-32466|脸型/下庭": "lower_face.amount"',
    '"PC-32466|脸型/下巴长短": "chin_length.amount"', '"PC-32466|脸型/尖下巴": "chin_shape.v1"',
    '"PC-32466|脸型/太阳穴": "face_contour.temple"', '"PC-32466|脸型/颧骨": "face_contour.cheekbone"',
    '"PC-32466|脸型/下颌": "face_contour.jaw"', '"PC-32466|脸型/收下巴": "deform.small_chin"',
    '"PC-32466|眉毛": "brow.family"', '"PC-32466|鼻子": "nose.family"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }',
    '<ChinLengthControl key={leaf.path}', '<LegacySmallChinControl key={leaf.path}',
    '与新版瘦脸或新版下巴长短的非零效果冲突时引擎会拒绝整个请求']) assert.ok(panel.includes(original));
  assert.ok(source('../chinLength/model.ts').includes('return [legacySmallChinPatch(0), chinLengthPatch(value)]'));
  assert.ok(source('../chinLength/ChinLengthControl.tsx').includes('dispatch(replaceLegacySmallChinPatches(value))'));
});

test('unmanaged documents refuse rather than fall back to mouth position, another face warp or a native mutation', () => {
  for (const text of ['if (!doc?.people) return <section', '人中暂不可用',
    '不会改用嘴巴上下位置、中庭、下庭、下巴长短或尖下巴替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'resize(', 'runCrop', 'setStrength', 'amounts.small_chin']) {
    assert.equal(branch.includes(forbidden), false);
    assert.equal(control.includes(forbidden), false);
  }
  for (const forbidden of ['<MidFaceControl', '<LowerFaceControl', '<ChinLengthControl', '<MouthShapeControl']) {
    assert.equal(branch.includes(forbidden), false);
  }
  for (const forbidden of ['../midFace/', '../lowerFace/', '../chinLength/', '../mouthShape/']) {
    assert.equal(control.includes(forbidden), false);
    assert.equal(model.includes(forbidden), false);
  }
});

test('dedicated capability and competing-editor fences feed the one canonical people owner', () => {
  assert.ok(source('../native.ts').includes('philtrum_available?: boolean'));
  assert.ok(source('../native.ts').includes('philtrum_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.philtrum.v1': '人中（鼻下至唇上局部间距）'"));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'dispatch([philtrumPatch(value)])',
    'dispatch(philtrumResetPatches())']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'latestIntent', 'runPeopleRequest']) {
    assert.equal(control.includes(forbidden), false);
  }
});

test('effective/provenance and explicit/blank shared choices never collapse into a borrowed neutral baseline', () => {
  for (const text of ["const source = resolved.operations[PHILTRUM_OPERATION]?.['/amount']",
    "target?.scope === 'face' ? reading.value : null", 'reading.overridePresent ? reading.override']) assert.ok(model.includes(text));
  for (const text of ['targetLabel(view)', 'display(reading.value)', 'provenance(view, reading.source)',
    'display(reading.override)', 'access.editValue !== null', 'value={access.editValue * 100}',
    "useState('')", 'parsePhiltrumChoice(text)', 'choice === null', 'onChoose(choice)',
    'min={-100} max={100}', 'onChange={value => commit(value / 100)}',
    '不把所选人脸的继承参数复制给其他人物']) assert.ok(control.includes(text));
  for (const forbidden of ['reading.value ?? 0', 'access.editValue ?? 0', 'neutralPhiltrum()', 'onBlur=',
    'setLinked', 'left:', 'right:']) assert.equal(control.includes(forbidden), false);
});

test('source and owner changes invalidate drafts while stale callbacks and repeated submissions cannot retarget', () => {
  for (const text of ['owner.current.patch !== people.patch || owner.current.check !== people.check',
    'owner.current.generation + 1', 'philtrumBindingKey(view), owner.current.generation',
    'mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch && current.current.check === people.check',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:amount`}', 'key={`${binding}:choice`}',
    'current.current.access.resetDisabled : current.current.access.changeDisabled']) assert.ok(control.includes(text));
  assert.ok(model.includes('view.groups, view.persons, view.links'));
});

test('uncertain outcomes query the original receipt and expose unaltered engine refusals', () => {
  for (const text of ['people.check()', 'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）',
    'people.state.message', 'view?.refusals?.map', '{refusal.reason}', '以下保留引擎原始原因']) assert.ok(control.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('neutral action writes only philtrum zero with no anatomy/native requirement or legacy migration', () => {
  const reset = control.slice(control.indexOf('function resetAmount()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(philtrumResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'editValue']) assert.equal(reset.includes(forbidden), false);
  assert.ok(model.includes('return [philtrumPatch(0)]'));
  assert.ok(control.includes('choice === 0 ? resetDisabled : changeDisabled'));
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={resetAmount}'));
  for (const text of ['缺少核心、有效读数或面部分析时仍可归零', '归零写入中性覆盖，不恢复继承',
    '不迁移或重置任何旧操作']) assert.ok(control.includes(text));
  for (const forbidden of ["'lnx.deform.v1'", "'lnx.mid_face.v1'", "'lnx.lower_face.v1'",
    "'lnx.chin_length.v1'", "'lnx.mouth_shape.v1'", 'unset: true', 'replaceLegacy']) assert.equal(model.includes(forbidden), false);
});

test('source plane-gap policy, composition limitations, conservative refusal and unrun acceptance are explicit', () => {
  for (const text of ['正值拉长，负值缩短，0 无效果', '不是嘴巴上下位置、中庭、下庭、下巴长短或尖下巴的别名',
    '当前有效来源图像（原图或已返回合成图）', '全部 24 个鼻部顶点下方', '全部 40 个嘴唇顶点上方',
    '留出边界余量', '不是鼻点 2 至唇点 0 的简单距离', '不是临床人中长度或精确解剖分割',
    '本次新增映射保持固定上边界以上的实测鼻部不动', '同高度脸颊也可能改变',
    '嘴唇和下方脸部在横向核心区共同等量平移', '再向颈部与背景平滑衰减',
    '不是只移动上唇', '不是只对人中皮肤进行分割后变形', '头部倾斜时画面横坐标仍可能改变',
    '先前几何编辑可能已把鼻部或其他像素移入本次过渡带', '不承诺最终叠加结果',
    '不是 AI 重建、3D 塑颜或新增分割', 'P ≤ 8', '较短间隙可能被拒绝',
    '不能保证所有正面人像可用', '没有实拍拒绝比例数据', '不捏造间隙长度、可见性或质量测量',
    '核心就绪不代表此脸或当前组合可用', '不绕过手动液化等兼容性限制',
    '显示 -100 至 100 对应内部 -1 至 1', '不是官方标定或实测解剖比例',
    '均未运行（UNRUN）', '面部重塑功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['philtrum_applied', 'philtrum_facts', 'support_px', 'composition_available',
    'skipCompatibility', 'mid_face_available', 'lower_face_available', 'LocalEndpointRatio']) {
    assert.equal(model.includes(invented), false);
    assert.equal(control.includes(invented), false);
  }
});
