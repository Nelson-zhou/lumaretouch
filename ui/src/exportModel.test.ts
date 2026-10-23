/** Source-only fixtures, NOT RUN in the PNG16 implementation slice.
 * Qoder: node --experimental-strip-types --test src/exportModel.test.ts
 * These cover UI intent and transport wiring, not encoder/readback acceptance. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { exportGpsForDepth, is16BitExportFormat, reconcileExportCombo, reconcileExportFormat } from "./exportModel.ts";
import { destinationPort, type Invoke } from "./exportDestination/nativePort.ts";
import { initialDestination, type DestinationPreview } from "./exportDestination/model.ts";

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
  const select = app.slice(app.indexOf("<select value={exportFormat}"), app.indexOf('<option value="jpg"'));
  assert.match(select, /reconcileExportFormat\(exportBits16, e\.target\.value\)/);
  assert.doesNotMatch(select, /disabled=/);
  assert.match(app, /<option value="png">PNG<\/option>/);
  assert.match(app, /<option value="tif">TIFF<\/option>/);
  assert.match(app, /<option value="jpg" disabled=\{exportBits16\}>/);
  assert.match(app, /<option value="webp" disabled=\{exportBits16\}>/);
  assert.match(app, /\["tif", "tiff"\]\.includes\(exportFormat\) && <label>TIFF/);
  assert.match(app, /<ExportMetadataOptions bits16=\{exportBits16\} format=\{exportFormat\}/);
  assert.match(metadata, /onFormat\(reconcileExportFormat\(e\.target\.checked, format\)\)/);
  assert.doesNotMatch(metadata, /onFormat\("tif"\)/);
  assert.match(metadata, /checked=\{exportGpsForDepth\(bits16, gps\)\} disabled=\{bits16\}/);
  assert.match(app, /disabled=\{exportBits16 \|\| exportTargetSize\.enabled/);
  assert.match(app, /<TargetSizeControls[^>]*format=\{exportFormat\} bitDepth=\{exportBits16 \? 16 : 8\}/);
});

test("destination preview and submit share format, bit depth, compression and GPS intent", () => {
  const app = source("./App.tsx");
  const preview = app.slice(app.indexOf("function destinationOptions()"), app.indexOf("async function onPreviewDestination()"));
  const submit = app.slice(app.indexOf("async function onExport()"), app.indexOf("async function watchExportOutcome("));
  for (const block of [preview, submit]) {
    assert.match(block, /reconcileExportCombo\(exportBits16,\s*exportFormat,\s*exportTiffComp\)/);
    assert.match(block, /format:\s*combo\.format/);
    assert.match(block, /exportGpsForDepth\(exportBits16, exportGps\)/);
  }
  assert.match(preview, /bit_depth:16/);
  assert.match(preview, /combo\.tiffCompression \? \{tiff_compression:combo\.tiffCompression\} : \{\}/);
  assert.match(submit, /bitDepth:exportBits16 \? 16 : undefined/);
  assert.match(submit, /tiffCompression:combo\.tiffCompression/);
  const signature = app.slice(app.indexOf("const destinationSignature"), app.indexOf("destinationInput.current = destinationSignature"));
  for (const field of ["exportFormat", "exportBits16", "exportTiffComp", "exportGps"]) assert.ok(signature.includes(field));
});

test("alternate registry controls preserve 16-bit intent and hide incompatible formats", () => {
  const app = source("./App.tsx");
  assert.match(app, /\.filter\(x=>!exportBits16\|\|is16BitExportFormat\(x\)\)/);
  assert.match(app, /setExportFormat\(reconcileExportFormat\(exportBits16, fmtOut\[v\] \?\? v\)\)/);
  assert.match(app, /if \(!exportBits16\) setExportGps\(v\)/);
  assert.match(app, /key === "lnx\.export\.v1\.jpeg_quality" && exportBits16/);
});

test("queue uses actual returned depth/format or reconciled pending format, not a TIFF16 constant", () => {
  const queue = source("./components/ExportQueuePanel.tsx");
  assert.match(queue, /reconcileExportFormat\(exportBits16, exportFormat\)/);
  assert.match(queue, /done\.bits \?\? status\?\.export\?\.bit_depth/);
  assert.doesNotMatch(queue, /exportBits16 \? "16-bit TIFF"/);
});

test("native export and destination ports forward format/depth rather than forcing TIFF", () => {
  const native = source("./native.ts");
  const runExport = native.slice(native.indexOf("export const runExport ="), native.indexOf("export {parseFrameHead"));
  for (const field of ["format", "bitDepth", "tiffCompression"]) assert.ok(runExport.includes(`${field}: opts?.${field}`));
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
