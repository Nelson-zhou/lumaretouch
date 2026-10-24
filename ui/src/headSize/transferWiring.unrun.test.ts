// AUTHORED / UNRUN. Source wiring assertions are not mounted UI, browser or photo acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=(path:string)=>readFileSync(new URL(path,import.meta.url),'utf8');
test('head scalar has actual preset and batch review routes, not only a helper',()=>{
  const batch=source('../batch/BatchReview.tsx'),preset=source('../presets/PresetPanel.tsx'),hook=source('../presets/usePresetWorkflow.ts');
  for(const item of ['HeadTransferReview','head_transfer','headReady','HEAD_TRANSFER_OP']){
    assert.ok(batch.includes(item),item);assert.ok(preset.includes(item),item);
  }
  for(const item of ['headTransferReviewKey(`${review.preflight_token}:${review.request_id}`','!headReady','headReviewAck:headTransferAck','setHeadImage','moduleScope:[HEAD_TRANSFER_OP]'])assert.ok(hook.includes(item),item);
  assert.ok(batch.includes('`${plan?.preflight_token??\'\'}:${plan?.request_id??\'\'}`'));
  assert.ok(batch.includes('headTransferAck(headTargets.map(t=>t.head_transfer!))'));
  assert.ok(source('../batch/batchScopeOptions.ts').includes("ops:['lnx.head_size.v1']"));
  assert.ok(source('../presets/presetModel.ts').includes("'lnx.head_size.v1':"));
  assert.ok(source('../batch/useBatchWorkflow.ts').includes('commit(ack,shadowAck,torsoAck,waistAck,headAck)'));
});
test('head reuses verified and decoded PNG gating with independent head disclosures',()=>{
  const shared=source('../bodyScalar/BodyScalarTransferReview.tsx'),wrapper=source('./HeadTransferReview.tsx');
  assert.ok(wrapper.includes('BodyScalarTransferReview'));assert.ok(wrapper.includes('kind="head"'));
  for(const item of ['完整头发/头部框','缩小中心','外围过渡框','本人面部归属','不会复制源图几何'])assert.ok(wrapper.includes(item),item);
  for(const item of ['verifyBodyScalarTransferImage(value.before)','verifyBodyScalarTransferImage(value.after)',
    'image.naturalWidth===expected.width','image.naturalHeight===expected.height','viewed.checked','disabled={disabled||!ready}',
    '不会自动降低强度','不承诺 3D 等效','0 到 100'])assert.ok(shared.includes(item),item);
});
test('head remains query-only and carries camelCase acknowledgment to both native commands',()=>{
  const native=source('../native.ts');
  assert.equal(native.split('headReviewAck:opts.headReviewAck').length-1,2);
  assert.ok(source('../presets/PresetPanel.tsx').includes('w.ui.submitted?.options.headReviewAck===undefined'));
  assert.ok(source('../batch/BatchReview.tsx').includes('!plan?.module_scope.includes(HEAD_TRANSFER_OP)&&<button'));
  assert.ok(source('../presets/presetWorkflow.ts').includes('if(pending?.options.headReviewAck!==undefined)'));
  assert.ok(source('../batch/batchWorkflow.ts').includes('if(pending?.headAck!==undefined)'));
});
