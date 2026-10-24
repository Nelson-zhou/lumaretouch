// AUTHORED / UNRUN. Source-contract fixtures only, not mounted interaction, type checking or runtime acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const panel = source('../components/RetouchPanel.tsx'), control = source('./ChinShapeControl.tsx');
const model = source('./model.ts');
const branch = panel.slice(panel.indexOf('case "chin_shape.v1":'), panel.indexOf('case "face_contour.temple":'));

test('only exact 尖下巴 routes to the distinct operation; all old routes and historical presets remain', () => {
  assert.ok(source('../spec/refine.json').includes('"path": "脸型/尖下巴"'));
  assert.ok(panel.includes('"PC-32466|脸型/尖下巴": "chin_shape.v1"'));
  assert.equal((panel.match(/"PC-32466\|[^"\n]+": "chin_shape\./g) ?? []).length, 1);
  assert.ok(branch.includes('<ChinShapeControl key={leaf.path}'));
  assert.ok(control.includes('data-control-id={CHIN_SHAPE_CONTROL_ID}'));
  assert.ok(model.includes("CHIN_SHAPE_OPERATION = 'lnx.chin_shape.v1'"));
  assert.ok(model.includes("CHIN_SHAPE_CONTROL_ID = 'LNX-REF-PC-32466-C-ed7837df9a'"));
  for (const original of ['"PC-32466|脸型/瘦脸": "slim_face.v2"', '"PC-32466|脸型/小脸": "face_size.amount"',
    '"PC-32466|脸型/中庭": "mid_face.amount"', '"PC-32466|脸型/下庭": "lower_face.amount"',
    '"PC-32466|脸型/太阳穴": "face_contour.temple"', '"PC-32466|脸型/颧骨": "face_contour.cheekbone"',
    '"PC-32466|脸型/下颌": "face_contour.jaw"', '"PC-32466|脸型/收下巴": "deform.small_chin"',
    '"PC-32466|眉毛": "brow.family"', '"PC-32466|鼻子": "nose.family"',
    '"PC-32466|眼睛": "eye.family"', '"PC-32466|嘴巴": "mouth.family"',
    '经典: { slim_face: 0.22, big_eye: 0.04, small_chin: 0.14, smile: 0 }',
    '幼态: { slim_face: 0.12, big_eye: 0.10, small_chin: 0.10, smile: 0.05 }',
    '英气: { slim_face: 0.30, big_eye: 0.02, small_chin: 0.18, smile: 0 }']) assert.ok(panel.includes(original));
});

test('unmanaged documents explicitly refuse without any alias, legacy migration or alternate execution', () => {
  for (const text of ['if (!doc?.people) return <section', '尖下巴暂不可用',
    '不会改用旧版小下巴、收下巴、下巴长短、下庭、瘦脸或下颌替代']) assert.ok(branch.includes(text));
  for (const forbidden of ['runDeform', 'runHistory', 'invoke(', 'resize(', 'runCrop', 'setStrength', 'amounts.small_chin']) {
    assert.equal(branch.includes(forbidden), false); assert.equal(control.includes(forbidden), false);
  }
  for (const forbidden of ['<LowerFaceControl', '<MidFaceControl', '<SlimFaceControl']) assert.equal(branch.includes(forbidden), false);
  for (const operation of ["'lnx.deform.v1'", "'lnx.lower_face.v1'", "'lnx.mid_face.v1'", "'lnx.face_contour.v1'"])
    assert.equal(model.includes(operation), false);
});

test('dedicated capabilities and competing-editor fences feed only the existing people owner', () => {
  assert.ok(source('../native.ts').includes('chin_shape_available?: boolean'));
  assert.ok(source('../native.ts').includes('chin_shape_reason?: string | null'));
  assert.ok(source('../people/model.ts').includes("'lnx.chin_shape.v1': '尖下巴（局部横向收尖，左右独立）'"));
  for (const text of ['people={props.people}', 'capability={status?.ready_caps}', 'blocked={dim',
    'props.hairBusy', 'props.whiteBalanceBusy', 'portraitRequestsBusy()', 'status?.edit_queue?.in_flight',
    'status?.edit_queue?.pending', 'status?.edit_queue?.closed', 'faceOk={props.faceOk}', 'faceWhy={props.faceWhy}']) assert.ok(branch.includes(text));
  for (const text of ['enabled: people.enabled', 'pending: people.state.pending', 'uncertain: people.state.uncertain',
    'externalBusy: blocked', 'people.patch(patches)', 'dispatch(chinShapeAdjustPatches(side, value, linked))',
    'dispatch(chinShapeLinkedPatches(value))', 'dispatch([chinShapeUnlockPatch()])',
    'dispatch(chinShapeResetPatches())']) assert.ok(control.includes(text));
  assert.equal((control.match(/people\.patch\(/g) ?? []).length, 1);
  for (const forbidden of ['createPeopleWorkflow', 'people.submit(', 'people.submitCaptured(', 'runPeopleRequest'])
    assert.equal(control.includes(forbidden), false);
});

test('selected provenance, shared explicit values and raw blank choices are kept distinct', () => {
  for (const text of ['resolved.operations[CHIN_SHAPE_OPERATION]?.[path]',
    "item.overridePresent ? item.override : target?.scope === 'face' ? item.value : null"]) assert.ok(model.includes(text));
  for (const text of ['targetLabel(view)', 'display(item.value)', 'provenance(view, item.source)',
    'display(item.override)', 'access.editLeft', 'access.editRight', 'value={value * 100}',
    "useState('')", 'parseChinShapeChoice(text)', 'choice === null', 'onChoose(choice)',
    'min={-100} max={100}', '不把所选人脸的继承参数复制给其他人物']) assert.ok(control.includes(text));
  for (const forbidden of ['reading.left.value ?? 0', 'access.editLeft ?? 0', 'neutralChinShape()', 'onBlur=',
    'value={item.value * 100}', 'value={reading.left.value']) assert.equal(control.includes(forbidden), false);
});

test('linking requires an explicit equal new choice, while unlock and neutral preserve old values or mode', () => {
  for (const text of ['recipe.linked && recipe.left !== recipe.right',
    "parameter_path: '/linked', unset: false, value: true}, ...sides]",
    "parameter_path: '/linked', unset: false, value: false}",
    'CHIN_SHAPE_SIDES.map(side => chinShapeAmountPatch(side, 0))']) assert.ok(model.includes(text));
  for (const text of ['access.editLeft !== null && access.editLeft === access.editRight',
    'onChoose={linkWithChoice}', '解除联动，独立调整左右', '重新联动必须明确选择一个新数值',
    '同一请求写入联动和相同的左右值', '不保证不对称人脸的视觉结果相同']) assert.ok(control.includes(text));
  assert.equal(control.includes('setLinked(true)'), false);
  assert.equal(model.includes('Math.round'), false);
});

test('late callbacks, owner replacements, stale drafts and repeated clicks cannot retarget writes', () => {
  for (const text of ['mounted.current && current.current.binding === binding', 'mounted.current = false',
    'current.current.patch === people.patch', 'current.current.check === people.check',
    'owner.current.generation + 1', 'chinShapeBindingKey(view), owner.current.generation',
    'if (!stillCurrent() || submitted.current) return', 'submitted.current = true', '}, [binding, people.state])',
    'key={`${binding}:linked`}', 'key={`${binding}:linked-choice`}', 'key={`${binding}:${side}:choice`}',
    'key={`${binding}:relink-choice`}',
    'current.current.access.resetDisabled : current.current.access.changeDisabled',
    'people.check()', 'if (stillCurrent()) note(String(error))', '查询原请求结果（不重发修改）']) assert.ok(control.includes(text));
  const workflow = source('../people/workflow.ts');
  for (const text of ["action: 'patch', payload: {patches}", 'command.document_epoch === current.binding.document_epoch',
    'command.document_revision === current.binding.document_revision', 'command.state_revision === current.revision',
    'command.association_revision === current.association_revision', 'reply.request_id !== command.request_id',
    'result.action !== command.action', 'result.document_id !== command.document_id', 'result.outcome_unknown',
    'view.uncertain', 'queued = null; waitFor = null;']) assert.ok(workflow.includes(text));
});

test('neutral action remains separate from disabled number controls, with ownership but no anatomy/core gate', () => {
  const reset = control.slice(control.indexOf('function resetBoth()'), control.indexOf('function checkOriginal()'));
  assert.ok(reset.includes('if (!stillCurrent() || current.current.access.resetDisabled) return'));
  assert.ok(reset.includes('dispatch(chinShapeResetPatches())'));
  for (const forbidden of ['changeDisabled', 'core.available', 'faceOk', 'reading.', 'writeLinked']) assert.equal(reset.includes(forbidden), false);
  assert.ok(control.includes('disabled={access.resetDisabled} onClick={resetBoth}'));
  assert.ok(control.includes('缺少核心、有效读数或面部分析时仍可归零'));
  assert.ok(control.includes('归零写入中性覆盖，不恢复继承'));
});

test('direction, source-owned support, native limits and explicit visual risks are honest', () => {
  for (const text of ['正值向内收尖，负值向外扩展、趋于圆润', '下巴下部的横向轮廓',
    '不是下巴长短、收下巴、下庭、小脸、瘦脸、V 脸或下颌调整', '人物自身左右侧',
    '不沿头部局部纵向移动下巴', '头部倾斜时不能据此承诺画面纵坐标不变',
    '不承诺先前几何叠加后的下巴位置不变', '当前有效来源图像（原图或已返回合成图）',
    '每个目标自己的下巴支撑范围由渲染器重新计算', '界面不提供测量值',
    '不把核心就绪当成可见性、解剖有效性或照片质量的证明',
    '不是 AI 重建、3D 塑颜、骨骼矫正或精确曲率控制', '不补造遮挡、截断或画面外的部位',
    '邻近背景、颈部及边缘过渡带可能移动', '倾斜、侧转、遮挡、裁切和相邻人脸',
    '已有几何与当前有效来源由引擎统一检查和组合', '界面不绕过手动液化等兼容性限制',
    '核心就绪不代表此脸、每一侧或当前组合可用', '以下保留引擎原始原因',
    'view?.refusals?.map', '{refusal.reason}', '旧版小下巴及历史脸型预设保留原含义，不自动转换为尖下巴',
    '显示 -100 至 100 对应内部 -1 至 1', '不是手册规定', '不是官方标定',
    '均未运行（UNRUN）', '面部重塑功能族仍未完整验收']) assert.ok(control.includes(text));
  for (const invented of ['chin_shape_applied', 'chin_shape_facts', 'support_px', 'composition_available',
    'manual_liquify_available', 'skipCompatibility', 'lower_face_available', 'face_size_available', 'face_contour_available']) {
    assert.equal(model.includes(invented), false); assert.equal(control.includes(invented), false);
  }
});
