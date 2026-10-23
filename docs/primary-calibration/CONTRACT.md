# RGB primary calibration: source connected, UNRUN

Scope: PC-32455-C-45230cc916, three primary groups and six hue/saturation children. This is not HSL, selective color, ICC loading, DCP profiling, RAW camera calibration, or a claim to match proprietary pixels.

## Design and provenance
Original std-only Rust float32 numeric implementation. Existing Lumaretouch colour-grading transport/history boilerplate was adapted, not its color algorithm. Mature design reference: darktable official RGB primaries manual, consulted 2026-10-23, https://docs.darktable.org/usermanual/4.6/en/module-reference/processing-modules/rgb-primaries/ . Its documented principles distinguish global primary changes, neutral gray preservation, and pre-tone-map colorimetric placement. No third-party implementation was copied. This module omits tint controls intentionally because the mapped requirement is six primary controls.

The stored working space is linear sRGB D65. Six sliders are -100..100. Hue maps to +/-20 degrees in xy around D65; saturation maps to radial scale 0.5..1.5. Each new primary is represented by [x/y,1,(1-x-y)/y]. Solve new column luminance weights from D65; construct the new RGB-to-XYZ basis, then transform using inverse(original basis) * new basis. This is not per-pixel HSL conversion. Neutral controls return exact input; exact gray pixels remain bit-identical, including signed and >1 gray.

## Strict admission
All six scalars finite/ranged; exact version, algorithm, space, keys. Changed xy must be inside positive physical chromaticity triangle; positive determinant >1e-5, infinity condition number <=100, white weights 0.005..2.0, and final transform must pass matrix admission. A valid slider interval does not mean all six-knob combinations are admissible. Invalid combinations fail visibly; never clamp or silently neutralize recipes. UI syntactic validation is not numerical admission. Rust is authoritative, called by stage creation, preset and project validation. Missing native library blocks active edits/imports, not legacy neutral rendering.

## Pixel contract
Mode 0 accepts linear sRGB D65 signed float32 up to absolute 65504. Mode 1 accepts extended encoded sRGB D65 signed float32 up to absolute 128 and uses sign-preserving sRGB transfer functions. Values outside [0,1] are not clipped in float output. Source profile conversion must happen upstream; arbitrary ICC/P3/Rec.2020 cannot be relabeled sRGB. Rust ABI accepts <=65536 pixels per chunk, bounds/alignment/alias checks; Python owns valid pointers and chunk cancellation. Buffers never publish partially.

RGB8/RGB16 adapter uses float32 normalization at its actual 255/65535 maximum and clips only for final integer quantization. For host/export pipelines select float path whenever active to avoid intermediate clipping; GPU tensor adapter returns float32 with an explicit CPU roundtrip. No GPU speed claim. Neutral stage returns original array/tensor without copies or transfers. Incoming alpha is unsupported and must remain outside this RGB-only stage.

## Stage placement
Insert after apply_exposure (which includes WB) and before extended-tone-input early return, extended tone, levels, curves, HSL and LUT. Both normal preview and extended-tone full-frame export prepass must include calibration at this same boundary. When export uses a precomputed extended-tone override, it must not apply calibration twice to that override. Configure every per-tile pipeline with the recipe, including prepass pipeline; do not append a separate final export stage. Calibration is spatially uniform and requires no ROI/geometry adjustment.

## Safety and state
One pending preview, replaceable latest intent, immediate reader cancellation, bounded mailbox, exact request/document/revision/engine epoch/seq/slot/presentation correlation. Commit only displayed preview and one history record; uncertain submissions are queried, not replayed. Temporary preview stage does not persist. Restore/undo/project/batch install replace recipes, not accumulate matrices. Explicit null/invalid recipe fails; only missing legacy key is neutral. Project v19 stores the new key; v18 selective, v17 grading, v16 tone, v15 CUBE and v14 hair gates are preserved. Older schemas reject a present primary-calibration key; omitted legacy key remains neutral.

## Verification boundary
No product imports, execution, tests, compiler, typecheck, build, inference, installs, downloads, Git writes or push were performed. Static Python AST/JSON/source/hash inspection only. Native UI, engine, persistence, scoped batch/presets and packaging are connected in source. UNRUN fixtures are design assets, not passed tests. ABI compilation, visual/HDR/RGB16 consistency, concurrency, project migration, preview/export parity and performance remain to be executed by the authorized local tester.
