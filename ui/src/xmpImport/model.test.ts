// AUTHORED / UNRUN. Synthetic protocol fixtures are not photo/render acceptance.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {XMP_MODE, validXmpAck, validXmpReport, validXmpSummary, validXmpTransfer, validXmpReviewAck,
  verifyXmpPreview, xmpReviewAck, xmpReviewKey, type XmpReport, type XmpSummary, type XmpTransfer} from './model.ts';

const hash = (letter: string) => letter.repeat(64);
const report = (): XmpReport => ({version: 1, source_sha256: hash('a'), report_sha256: hash('b'), filename: 'sample.xmp', byte_length: 512,
  process_version: '11.0', camera_raw_version: '15.0', can_import: true,
  properties: [{name: 'ProcessVersion', status: 'unsupported', value: '11.0', reason: 'Syntax only, no Adobe emulation'},
    {name: 'Exposure2012', status: 'adaptable', value: '1.25', reason: 'Native EV reinterpretation'},
    {name: 'WhiteBalance', status: 'unsupported', value: 'As Shot', reason: 'No reference/gains inference'}],
  adaptations: [{id: 'exposure', title: 'Native EV', module: 'lnx.exposure.v1', reason: 'Explicit selection only'}],
  warnings: ['No Adobe rendering equivalence']});
const summary = (): XmpSummary => ({version: 1, source_sha256: hash('a'), filename: 'sample.xmp', selected: ['exposure'], report: report(), read_only_summary: true});
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2ioAAAAASUVORK5CYII=';
const pngHash = createHash('sha256').update(Buffer.from(png, 'base64')).digest('hex');
const transfer = (): XmpTransfer => ({version: 1, document_id: 'photo', revision: '7', xmp_sha256: hash('a'),
  source_proof: {asset_sha256: hash('c'), original_sha256: hash('c'), creative_source: null},
  before_sha256: hash('d'), candidate_sha256: hash('e'), before_people_sha256: hash('f'), candidate_people_sha256: hash('f'),
  source_size: [100, 100], before_output_size: [100, 100], after_output_size: [100, 100],
  before: {mime: 'image/png', width: 1, height: 1, sha256: pngHash, base64: png},
  after: {mime: 'image/png', width: 1, height: 1, sha256: pngHash, base64: png}});

test('supported syntax does not hide unsupported white balance or process reporting', () => {
  const value = report(); assert.equal(validXmpReport(value), true);
  assert.equal(value.properties.find(row => row.name === 'WhiteBalance')?.status, 'unsupported');
  value.process_version = 'future-version'; value.can_import = false; value.adaptations = [];
  assert.equal(validXmpReport(value), true);
  assert.equal(validXmpAck({mode: XMP_MODE, source_sha256: hash('a'), report_sha256: hash('b'), selected: ['exposure']}, value), false);
  value.can_import = true; assert.equal(validXmpReport(value), false);
});
test('legitimate bounded large unsupported values, structured values and Unicode remain visible', () => {
  const value = report();
  value.process_version = 'v'.repeat(200); value.can_import = false; value.adaptations = [];
  value.properties.push({name: '{https://example.invalid/ns/}' + 'n'.repeat(900), status: 'unsupported',
    value: {kind: 'structure', fields: {LookTable: '🎨'.repeat(65536)}}, reason: 'Inert unsupported payload'});
  assert.equal(validXmpReport(value), true);
  value.properties[3].value = 'x'.repeat(65537); assert.equal(validXmpReport(value), false);
});
test('public report rejects raw source bytes, unsafe filenames, malformed hashes and excess bounds', () => {
  for (const patch of [{source_base64: 'PHhtcD4='}, {source_sha256: 'A'.repeat(64)}, {filename: '../sample.xmp'},
    {filename: 'x\\sample.xmp'}, {byte_length: 1048577}, {properties: Array(513).fill(report().properties[0])},
    {adaptations: [{id: 'white_balance', title: 'WB', module: 'lnx.white_balance.v1', reason: 'not admitted'}]}]) {
    assert.equal(validXmpReport({...report(), ...patch}), false);
  }
});
test('each import acknowledgement binds both hashes and a nonempty unique admitted selection', () => {
  const ack = {mode: XMP_MODE, source_sha256: hash('a'), report_sha256: hash('b'), selected: ['exposure']};
  assert.equal(validXmpAck(ack, report()), true);
  for (const patch of [{selected: []}, {selected: ['exposure', 'exposure']}, {selected: ['point_curves']},
    {source_sha256: hash('c')}, {report_sha256: hash('c')}, {mode: 'adobe-compatible'}, {extra: true}]) {
    assert.equal(validXmpAck({...ack, ...patch}, report()), false);
  }
});
test('public summary is read-only and binds selected groups to exact native modules', () => {
  assert.equal(validXmpSummary(summary(), ['lnx.exposure.v1']), true);
  assert.equal(validXmpSummary(summary(), ['lnx.exposure.v1', 'lnx.white_balance.v1']), false);
  assert.equal(validXmpSummary({...summary(), source_base64: 'PHhtcD4='}), false);
  assert.equal(validXmpSummary({...summary(), read_only_summary: false}), false);
  assert.equal(validXmpSummary({...summary(), source_sha256: hash('c')}), false);
});
test('target report binds document, revision, XMP, effective source and both output sizes', () => {
  assert.equal(validXmpTransfer(transfer(), 'photo', '7', hash('a')), true);
  for (const patch of [{document_id: 'other'}, {revision: '8'}, {xmp_sha256: hash('c')}, {source_proof: {}},
    {before_people_sha256: ''}, {candidate_people_sha256: ''}, {after_output_size: [0, 1]}, {extra: true}]) {
    assert.equal(validXmpTransfer({...transfer(), ...patch}, 'photo', '7', hash('a')), false);
  }
  const derived = transfer(); derived.source_proof.creative_source = {sha256: hash('c'), width: 100, height: 100};
  derived.source_proof.original_sha256 = hash('d'); assert.equal(validXmpTransfer(derived, 'photo', '7', hash('a')), true);
  derived.source_proof.creative_source.width = 101; assert.equal(validXmpTransfer(derived, 'photo', '7', hash('a')), false);
});
test('missing, substituted, oversized or wrong-aspect previews cannot be accepted as a pair', () => {
  for (const side of ['before', 'after'] as const) {
    for (const patch of [{mime: 'image/svg+xml'}, {width: 641}, {width: 0}, {height: 1.5}, {sha256: ''},
      {base64: 'https://example.invalid/pixel.png'}, {base64: 'iVBOR' + 'A'.repeat(1398104)}]) {
      const value = transfer(); Object.assign(value[side], patch);
      assert.equal(validXmpTransfer(value, 'photo', '7', hash('a')), false);
    }
  }
});
test('PNG byte hashes and IHDR dimensions are verified independently of load events', async () => {
  const value = transfer(); assert.equal(await verifyXmpPreview(value.before), true);
  assert.equal(await verifyXmpPreview({...value.before, sha256: hash('0')}), false);
  assert.equal(await verifyXmpPreview({...value.before, width: 2}), false);
  assert.equal(await verifyXmpPreview({...value.before, base64: 'iVBORw=='}), false);
});
test('review acknowledgment uses rendered PNG hashes, never recipe hashes; identity changes invalidate readiness', () => {
  const value = transfer(), compatibility = report(), ack = xmpReviewAck(value, compatibility);
  assert.equal(validXmpReviewAck(ack), true); assert.equal(ack.before_sha256, value.before.sha256);
  assert.notEqual(ack.before_sha256, value.before_sha256);
  const key = xmpReviewKey('token-a', value, compatibility);
  assert.notEqual(key, xmpReviewKey('token-b', value, compatibility));
  for (const patch of [{revision: '8'}, {before_sha256: hash('0')}, {candidate_people_sha256: hash('0')}]) {
    assert.notEqual(key, xmpReviewKey('token-a', {...value, ...patch}, compatibility));
  }
  assert.notEqual(key, xmpReviewKey('token-a', value, {...compatibility, report_sha256: hash('0')}));
  assert.equal(validXmpReviewAck({...ack, arbitrary: true}), false);
});
