/** Source-only fixtures, NOT RUN in the PNG16 / Original format implementation slices.
 * Qoder: node --experimental-strip-types --test src/exportModel.test.ts
 * These cover UI intent and transport wiring, not encoder/readback acceptance. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { exportBitDepthForIntent, exportGpsForDepth, exportGpsForIntent, isOriginalExportFormat, is16BitExportFormat, reconcileExportCombo, reconcileExportFormat } from "./exportModel.ts";
import { destinationPort, type Invoke } from "./exportDestination/nativePort.ts";
import { decisionForEntry, initialDestination, originalFormatPlan, type DestinationPreview } from "./exportDestination/model.ts";

import {initialTargetSize, targetSizePolicy} from "./exportTargetSize/model.ts";

const source = (path: string) => readFileSync(new URL(path, import.meta.url), "utf-8");

for (const format of ["png", "tif", "tiff"]) {
  test(`enabling 16-bit preserves ${format}`, () => {
    assert.equal(is16BitExportFormat(format), true);
    assert.equal(reconcileExportFormat(true, format), format);
    assert.equal(reconcileExportFormat(false, format), format);
  });
}

for (const format of ["jpg", "jpeg", "webp"]) {
  test(`enabling 16-bit explicitly defaults unsupported ${format} to TIFF`, () => {
    assert.equal(is16BitExportFormat(format), false);
    assert.equal(reconcileExportFormat(true, format), "tif");
    assert.equal(reconcileExportFormat(false, format), format);
  });
}

for (const compression of ["none", "deflate", "lzw"]) {
  test(`PNG16 omits TIFF compression and returning to TIFF restores ${compression}`, () => {
    const png = reconcileExportCombo(true, "png", compression);
    assert.deepEqual(png, {format: "png", tiffCompression: undefined});
    assert.equal("tiffCompression" in JSON.parse(JSON.stringify(png)), false);
    assert.deepEqual(reconcileExportCombo(true, "tif", compression), {format: "tif", tiffCompression: compression});
    assert.deepEqual(reconcileExportCombo(true, "tiff", compression), {format: "tiff", tiffCompression: compression});
    assert.deepEqual(reconcileExportCombo(true, "jpg", compression), {format: "tif", tiffCompression: compression});
    assert.deepEqual(reconcileExportCombo(false, "png", compression), {format: "png", tiffCompression: undefined});
    assert.deepEqual(reconcileExportCombo(false, "jpg", compression), {format: "jpg", tiffCompression: undefined});
  });
}

test("PNG16 -> TIFF16 -> PNG16 -> PNG8 does not lose PNG or retained TIFF options", () => {
  let format = reconcileExportFormat(true, "png");
  assert.equal(reconcileExportCombo(true, format, "lzw").format, "png");
  format = reconcileExportFormat(true, "tif");
  assert.equal(reconcileExportCombo(true, format, "lzw").tiffCompression, "lzw");
  format = reconcileExportFormat(true, "png");
  assert.deepEqual(reconcileExportCombo(true, format, "lzw"), {format: "png", tiffCompression: undefined});
  assert.equal(reconcileExportFormat(false, format), "png");
});

test("16-bit suppresses GPS without clearing the remembered 8-bit preference", () => {
  for (const remembered of [true, false]) {
    assert.equal(exportGpsForDepth(true, remembered), false);
    assert.equal(exportGpsForDepth(false, remembered), remembered);
  }
});

test("controls allow PNG/TIFF at 16-bit rather than locking the format selector", () => {
  const app = source("./App.tsx");
  const metadata = source("./components/ExportMetadataOptions.tsx");
  const select = app.slice(app.indexOf("<select value={exportFormat}"), app.indexOf('<option value="original"'));
  assert.match(select, /reconcileExportFormat\(exportBits16, e\.target\.value\)/);
  assert.doesNotMatch(select, /disabled=/);
  assert.match(app, /<option value="png">PNG<\/option>/);
  assert.match(app, /<option value="tif">TIFF<\/option>/);
  assert.match(app, /<option value="jpg" disabled=\{exportBits16\}>/);
  assert.match(app, /<option value="webp" disabled=\{exportBits16\}>/);
  assert.match(app, /\["tif", "tiff", "original"\]\.includes\(exportFormat\) && <label>TIFF/);
  assert.match(app, /<ExportMetadataOptions bits16=\{exportBits16\} format=\{exportFormat\}/);
  assert.match(metadata, /onFormat\(reconcileExportFormat\(e\.target\.checked, format\)\)/);
  assert.doesNotMatch(metadata, /onFormat\("tif"\)/);
  assert.match(metadata, /checked=\{exportGpsForIntent\(bits16, format, gps\)\} disabled=\{!original && bits16\}/);
  assert.match(app, /disabled=\{explicitBits16 \|\| exportTargetSize\.enabled/);
  assert.match(app, /<TargetSizeControls[^>]*format=\{exportFormat\} bitDepth=\{exportBitDepthForIntent\(exportBits16, exportFormat\)\}/);
});

test("destination preview and submit share format, bit depth, compression and GPS intent", () => {
  const app = source("./App.tsx");
  const preview = app.slice(app.indexOf("function destinationOptions()"), app.indexOf("async function onPreviewDestination()"));
  const submit = app.slice(app.indexOf("async function onExport()"), app.indexOf("async function watchExportOutcome("));
  for (const block of [preview, submit]) {
    assert.match(block, /reconcileExportCombo\(exportBits16,\s*exportFormat,\s*exportTiffComp,\s*exportTiffCompChosen\)/);
    assert.match(block, /format:\s*combo\.format/);
    assert.match(block, /exportGpsForIntent\(exportBits16, exportFormat, exportGps\)/);
  }
  assert.match(preview, /bit_depth:16/);
  assert.match(preview, /combo\.tiffCompression \? \{tiff_compression:combo\.tiffCompression\} : \{\}/);
  assert.match(submit, /exportBitDepthForIntent\(exportBits16, combo\.format\) === 16 \? \{bitDepth:16\} : \{\}/);
  assert.match(submit, /tiffCompression:combo\.tiffCompression/);
  const signature = app.slice(app.indexOf("const destinationSignature"), app.indexOf("destinationInput.current = destinationSignature"));
  for (const field of ["exportFormat", "exportBits16", "exportTiffComp", "exportGps"]) assert.ok(signature.includes(field));
});

test("alternate registry controls preserve 16-bit intent and hide incompatible formats", () => {
  const app = source("./App.tsx");
  assert.match(app, /\.filter\(x=>!exportBits16\|\|is16BitExportFormat\(x\)\)/);
  assert.match(app, /setExportFormat\(reconcileExportFormat\(exportBits16, fmtOut\[v\] \?\? v\)\)/);
  assert.match(app, /if \(!explicitBits16\) setExportGps\(v\)/);
  assert.match(app, /key === "lnx\.export\.v1\.jpeg_quality" && explicitBits16/);
});

test("queue uses actual returned depth/format or reconciled pending format, not a TIFF16 constant", () => {
  const queue = source("./components/ExportQueuePanel.tsx");
  assert.match(queue, /reconcileExportFormat\(exportBits16, exportFormat\)/);
  assert.match(queue, /done\.bits \?\? \(status\?\.export\?\.requested_format !== 'original'/);
  assert.doesNotMatch(queue, /exportBits16 \? "16-bit TIFF"/);
});

test("native export and destination ports forward format/depth rather than forcing TIFF", () => {
  const native = source("./native.ts");
  const runExport = native.slice(native.indexOf("export const runExport ="), native.indexOf("export {parseFrameHead"));
  for (const field of ["format", "tiffCompression"]) assert.ok(runExport.includes(`${field}: opts?.${field}`));
  assert.match(runExport, /opts\?\.bitDepth === undefined \? \{\} : \{bitDepth: opts\.bitDepth\}/);
  const rust = source("../src-tauri/src/main.rs");
  const command = rust.slice(rust.indexOf("fn export("), rust.indexOf("fn precompute("));
  assert.match(command, /cmd\["format"\] = json!\(v\)/);
  assert.match(command, /cmd\["bit_depth"\] = json!\(v\)/);
  assert.match(command, /\("tiff_compression", tiff_compression\.map\(Value::from\)\)/);
  const destination = source("../src-tauri/src/export_destination_port.rs");
  assert.match(destination, /cmd\["export_options"\]=export_options\.ok_or/);
});

test("destination transport retains exact PNG16 options without TIFF-only compression", async () => {
  const calls: {command: string; payload: Record<string, unknown>}[] = [];
  const plan: DestinationPreview = {
    schema_version: "lrt.export-destination.v1", plan_id: "fixture-png16", intent_revision: 3,
    entries: [{item_id: "doc-1", source_path: "/photos/source.png", frame_receipt: "fixture-frame",
      target: "/exports/source.png", disposition: "write", renamed_from: null, missing_directories: []}],
  };
  const invoke: Invoke = async <T>(command: string, payload: Record<string, unknown>): Promise<T> => {
    calls.push({command, payload: JSON.parse(JSON.stringify(payload))});
    if (command === "export_destination_result") return {status: "ready", value: plan} as T;
    return {requested: true} as T;
  };
  const combo = reconcileExportCombo(true, "png", "lzw");
  const options = {format: combo.format, bit_depth: 16, metadata_include_gps: exportGpsForDepth(true, true),
    ...(combo.tiffCompression ? {tiff_compression: combo.tiffCompression} : {})};
  const result = await destinationPort(invoke).preview(initialDestination(), ["doc-1"], 3, options);
  assert.deepEqual(result, plan);
  assert.deepEqual(calls.map(call => call.command), ["export_destination", "export_destination_result", "export_destination_release"]);
  assert.deepEqual(calls[0].payload.exportOptions, {format: "png", bit_depth: 16, metadata_include_gps: false});
  assert.equal(calls[0].payload.intentRevision, 3);
  assert.deepEqual(calls[0].payload.documentIds, ["doc-1"]);
});


for (const remembered16 of [false, true]) {
  test(`Original keeps explicit precision preference ${remembered16} without sending it`, () => {
    const combo = reconcileExportCombo(remembered16, 'original', 'lzw');
    assert.equal(isOriginalExportFormat(combo.format), true);
    assert.equal(is16BitExportFormat(combo.format), false);
    assert.equal(reconcileExportFormat(remembered16, 'original'), 'original');
    assert.equal(exportBitDepthForIntent(remembered16, combo.format), undefined);
    assert.deepEqual(combo, {format: 'original', tiffCompression: 'lzw'});
    const intent = {format: combo.format,
      ...(exportBitDepthForIntent(remembered16, combo.format) === 16 ? {bit_depth: 16} : {})};
    assert.equal(Object.hasOwn(intent, 'bit_depth'), false);
    assert.equal(exportGpsForIntent(remembered16, 'original', true), true);
    assert.equal(exportBitDepthForIntent(remembered16, 'png'), remembered16 ? 16 : 8);
  });
}

test('Original target-size intent reaches engine unresolved; incompatible explicit formats do not silently drop it', () => {
  const draft = {...initialTargetSize, enabled: true};
  const policy = targetSizePolicy(draft, 'original', undefined);
  assert.equal(policy?.target_bytes, 2 * 1048576);
  assert.equal(draft.enabled, true);
  assert.throws(() => targetSizePolicy(draft, 'png', 8), /JPEG/);
  assert.throws(() => targetSizePolicy(draft, 'jpg', 16), /JPEG/);
});

function originalPreview(): DestinationPreview {
  const decisions = Object.fromEntries([['a', 'jpg', 8], ['b', 'png', 16]].map(([id, codec, bits]) => {
    const item = `document:${id}`;
    return [item, {schema: 'lrt.export-format-decision.v1', item_id: item, document_id: id,
      source_asset_id: `asset-${id}`, recipe_version_id: `recipe-${id}`, fact_id: 'a'.repeat(64), decision_id: 'b'.repeat(64),
      codec, bits, extension: codec, source_facts: {schema: 'lrt.export-source-facts.v1'}, effective_asset: {kind: 'encoded'},
      applicable_options: {quality: bits === 8, tiff_compression: false, gps: bits === 8, target_size: codec === 'jpg'}, options: {}}];
  }));
  return {schema_version: 'lrt.export-destination.v1', plan_id: 'c'.repeat(64), intent_revision: 4,
    settings_json: JSON.stringify({format: 'original', format_plan: {schema: 'lrt.export-format-plan.v1', requested_format: 'original', entries: decisions}}),
    entries: [
      {item_id: 'document:a', source_path: '/source/a.jpeg', frame_receipt: 'a', target: '/out/a.jpg', disposition: 'write', renamed_from: null, missing_directories: []},
      {item_id: 'document:b', source_path: '/source/b.png', frame_receipt: 'b', target: '/out/b.png', disposition: 'write', renamed_from: null, missing_directories: []},
      {item_id: 'document:b::clean', source_path: '/source/b.png', frame_receipt: 'b', target: '/out/clean/b.png', disposition: 'write', renamed_from: null, missing_directories: []},
      {item_id: 'layout::page-0001.png', source_path: '/source/a.jpeg', frame_receipt: 'a', target: '/out/layout/page-0001.png', disposition: 'write', renamed_from: null, missing_directories: []},
    ]};
}

test('Original preview renders engine decisions for primary/clean entries, never a global mixed depth', () => {
  const preview = originalPreview();
  const plan = originalFormatPlan(preview, true);
  assert.equal(decisionForEntry(plan, 'document:a')?.codec, 'jpg');
  assert.equal(decisionForEntry(plan, 'document:b')?.bits, 16);
  assert.equal(decisionForEntry(plan, 'document:b::clean')?.decision_id, decisionForEntry(plan, 'document:b')?.decision_id);
  assert.equal(decisionForEntry(plan, 'layout::page-0001.png'), undefined);
  assert.throws(() => originalFormatPlan({...preview, settings_json: undefined}, true), /冻结/);
  for (const patch of [{schema: 'unknown'}, {bits: '16'}, {codec: 'raw'}, {bits: 16, codec: 'jpg', extension: 'jpg'}, {fact_id: 'fake'}]) {
    const settings = JSON.parse(preview.settings_json!);
    Object.assign(settings.format_plan.entries['document:a'], patch);
    assert.throws(() => originalFormatPlan({...preview, settings_json: JSON.stringify(settings)}, true));
  }
  const missing = JSON.parse(preview.settings_json!);
  delete missing.format_plan.entries['document:b'];
  assert.throws(() => originalFormatPlan({...preview, settings_json: JSON.stringify(missing)}, true), /缺少/);
});

test('Original transport forwards intent only and requires returned engine decisions', async () => {
  const calls: {command: string; payload: Record<string, unknown>}[] = [];
  const plan = originalPreview();
  const invoke: Invoke = async <T>(command: string, payload: Record<string, unknown>): Promise<T> => {
    calls.push({command, payload: JSON.parse(JSON.stringify(payload))});
    return (command === 'export_destination_result' ? {status: 'ready', value: plan} : {requested: true}) as T;
  };
  const options = {format: 'original', quality: 95, tiff_compression: 'deflate', metadata_include_gps: true};
  await destinationPort(invoke).preview(initialDestination(), ['a', 'b'], 4, options);
  assert.deepEqual(calls[0].payload.exportOptions, options);
  assert.equal(Object.hasOwn(calls[0].payload, 'format_plan'), false);
  await assert.rejects(() => destinationPort(invoke).preview(initialDestination(), ['a'], 5, {...options, bit_depth: 8}), /bit_depth/);
  await assert.rejects(() => destinationPort(invoke).preview(initialDestination(), [], 5, options), /文档/);
});

test('Original UI is capability-gated and host guards do not resolve or accept client facts', () => {
  const app = source('./App.tsx');
  const metadata = source('./components/ExportMetadataOptions.tsx');
  const host = source('../src-tauri/src/export_destination_port.rs');
  assert.match(app, /value="original" disabled=\{!originalAvailable\}/);
  assert.match(app, /export_original_format_available === true/);
  assert.match(metadata, /checked=\{!original && bits16\} disabled=\{original\}/);
  assert.match(host, /command\.get\("bit_depth"\)\.is_some\(\)/);
  assert.match(host, /validate_original_intent/);
  assert.match(source('../src-tauri/src/main.rs'), /validate_original_intent\(&cmd, false, &ready\)/);
});


test('Original untouched TIFF preference is omitted so engine preserves per-entry 8/16 defaults', () => {
  for (const remembered16 of [false, true]) {
    assert.deepEqual(reconcileExportCombo(remembered16, 'original', 'deflate', false), {format: 'original', tiffCompression: undefined});
    assert.deepEqual(reconcileExportCombo(remembered16, 'original', 'lzw', true), {format: 'original', tiffCompression: 'lzw'});
  }
  assert.equal(reconcileExportCombo(true, 'tif', 'deflate', false).tiffCompression, 'deflate');
  assert.match(source('./App.tsx'), /exportTiffCompChosen/);
});
