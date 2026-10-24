// AUTHORED / UNRUN static guard fixtures; assertions have NOT been executed.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
test('new review is distinct from eye-light and legacy scalar routing', () => {
  const panel = source('./EyeBagPreservePanel.tsx'), retouch = source('../components/RetouchPanel.tsx');
  assert.match(panel, /eye_bag_preview/); assert.match(panel, /eye_bag_confirm/);
  assert.doesNotMatch(panel, /eye_light_review|eye_light_reference/);
  assert.match(retouch, /面部祛瑕疵\/祛眼袋\/保留卧蚕/);
  assert.match(retouch, /旧版祛眼袋（保留原值与原行为/);
  assert.match(panel, /parameter_path: '\/amount', unset: false, value: 0/);
});
test('loaded actual support/before/after and explicit ACK guard application', () => {
  const panel = source('./EyeBagPreservePanel.tsx');
  assert.match(panel, /\['support', 'before', 'after'\]/);
  assert.match(panel, /naturalWidth === meta.width/); assert.match(panel, /!ready \|\| !accepted/);
  assert.match(panel, /replace_legacy: replaceLegacy/); assert.match(panel, /查询原请求，不重复提交/);
});
test('drawing provides source-space widths, erase, true pan and a default hard core', () => {
  const editor = source('./RidgeSourceEditor.tsx');
  assert.match(editor, /\[feather, setFeather\] = useState\(0\)/);
  assert.match(editor, /zoom >= 32/); assert.match(editor, /scrollLeft = drag.current.left/);
  assert.match(editor, /destination-out/); assert.match(editor, /onPointerCancel/);
  assert.match(editor, /setPointerCapture/); assert.doesNotMatch(editor, /feather: 20/);
});
test('native reads bypass capture invalidation and recovery mutation fences', () => {
  for (const file of ['engine.rs', 'native_dispatch.rs', 'project_recovery_fence.rs'])
    assert.match(source(`../../src-tauri/src/${file}`), /people_api::eye_bag::read_only/);
  const host = source('../../src-tauri/src/receipt_host.rs');
  assert.match(host, /people_api::eye_bag::binding/); assert.match(host, /strict_failure_identity: true/);
});
