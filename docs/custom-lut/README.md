# Custom CUBE LUT implementation candidate (SOURCE CONNECTED; UNRUN)

Requirement: `LNX-REF-PC-32455-C-f8f5161c78`, with existing filter/strength neighbors `32319e81a4`, `4252c408a9`, `07b01ea60d`. Baseline: `67d319b3`; baseline source audit: `handbook-audit-2026-10-23/colour.md`, item 13. Source-authored modules below are not a claim of product completion. No compiler, typecheck, product import, test, inference, download, or installed dependency was run.

## Verified references and independent choices

Read Adobe's authored CUBE LUT Specification 1.0, sections 5–8 (official Adobe download was unavailable; authored document read from https://kono.phpage.fr/images/a/a1/Adobe-cube-lut-specification-1.0.pdf). Header keys precede samples and are unique; omitted domain endpoints independently default to zero/one; 1D tables independently map channels; RGB samples in 3D use red-fastest indexing. Numeric range is bounded by 1e37. Linear 1D and trilinear 3D are implemented; no inverse, shaper-combined Resolve dialect, log-space inference or unsupported directive is silently accepted.

Read mature OpenColorIO implementation at https://raw.githubusercontent.com/AcademySoftwareFoundation/OpenColorIO/main/src/OpenColorIO/fileformats/FileFormatIridasCube.cpp: explicit dimension, sample count and domain handling. No code copied from either source. No external LUT assets downloaded. Test identity and permutation tables are original synthetic fixtures.

Product limits: 32 MiB text, 250-byte lines, 1D 2–65536, 3D 2–65 (Adobe allows up to 256, which this bounded reader explicitly rejects). CRLF and indented full-line comments are compatibility extensions; bare CR within a line, inline comments, unknown keys, repeated fields, late headers and mixed 1D/3D are rejected. A hash inside a quoted title is preserved. Non-monotonic sample values are legal; arbitrary mathematical sample-order mistakes cannot be detected because the format has no coordinate labels. Structural header/data ordering and red-fastest interpretation are checked, not fictional detection of reordered unlabeled rows.

Active lookup clamps each input coordinate to its declared domain, but never clips output table values. Zero amount returns original pixels exactly. Blend is original*(1-amount)+sample*amount. HDR samples/negative output remain float; input-domain clamping is an intentional creative-LUT policy, not full HDR colour-management support. Working colour space is explicitly display-encoded sRGB; a LUT does not declare ICC/camera/log conversion, so no space is guessed. RGB16 must quantize only at the existing final exporter, not through an RGB8 preview. Existing built-in `ops/lut.py`, its neutral shortcut, GPU interpolation and clipping semantics are untouched.

## Modules

- `core/custom_lut/lib.rs`: original strict parser, double-precision interpolation and bounded opaque-handle C ABI. `build_custom_lut.sh` is authored but UNRUN.
- `custom_lut_native.py`: ABI gate, explicit handle lifetime, bounded scratch chunks, cancellation, no fallback/compiler/download. Float32/64 inputs only; output image budget 256 MiB (input image already belongs to caller), plus bounded chunk scratch. Large full-resolution images exceeding this must use host export tiles rather than silently downsampling. Caller owns full-frame memory budget and schedules CPU work off the UI thread.
- `custom_lut_library.py`: immutable SHA256-addressed bytes in private SQLite storage, local-file-only regular-file import (no symlink/FIFO/device), one read snapshot, bounded library (512 entries/256 MiB including hidden resources), list/rename/hide/undo-hide. Hidden content remains resolvable for undo/project references. No physical deletion/GC is implemented; reaching the cap gives an explicit error rather than removing referenced history.
- `custom_lut_recipe.py`: versioned strict recipe and embedded portable bytes for project/preset transfer; content hash validated, no arbitrary imported resource paths.
- `custom_lut_controller.py`: latest-intent, document and recipe-revision barriers; rendering before atomic host commit; same numerical exporter. Host callback must atomically push history and swap frame+recipe or leave both unchanged on error.
- `ui/src/customLut/CustomLutPanel.tsx`: real import/list/select/strength/rename/hide/undo controls through explicit transport ports, status/error/cancel, stale-document guards. No simulated thumbnails. Connected by nativePort and ConnectedCustomLutPanel.
- `ui/src-tauri/src/custom_lut_api.rs`: single native local picker, cancel returns null. No web path entry or URLs.

## Shared integration now authored

See `INTEGRATION.md` for actual shared routes, project v15, compact batch references, portable preset files, worker snapshot/spool support and retained bounds. The initial isolated candidate below has been integrated in source; every runtime check remains UNRUN.

## Authored acceptance fixtures, not results

`core/custom_lut/lib.rs` unit fixtures; `core/custom_lut/identity-2.cube`; `engine/tests/custom_lut_contract_test.py`. Run only under separately authorized Qoder/local testing. Required runtime acceptance additionally includes native picker cancellation/late close, duplicate filenames/content, I/O and DB-full failure, source moved after import, undo selection and zero strength, project/preset transfer to a clean library, batch transaction failure, RGB16 endpoint precision, preview/export parity, corrupt/missing recovery, CPU latency/peak RSS and cancel during parsing/render. Current parse is bounded but cancellation interrupts only before/after its single <=32 MiB native parse, not midway inside parser.

Shared routes are now authored; see INTEGRATION.md. Present status is SOURCE_CONNECTED_UNRUN, not accepted or completed.
