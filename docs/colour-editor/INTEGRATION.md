# Colour editor implementation and handoff

Status: integrated source, runtime/visual/packaging acceptance UNRUN. Base for
shared edits: 7e8d29e549abbf546a44b023186c7a56fa33e63e. No product imports,
compilers, typechecks, tests, builds, inference, downloads or Git writes occurred.

## Stage identity

The common source chain is geometry → reference → semantic → grading → selective
colour → colour editor → detail → source grain → monochrome. The editor operates
only on the assembled float32 original-source canvas. It never runs independently
on tiles or on its own previous output. Preview uses the existing source-grain
full-source decode/render/downsample path, preserving source-grain order and
render-then-resize delivery. Inspection renders the complete edited field before
ROI slicing. Delivery resize and sharpening follow the full source chain whenever
the editor or grain is active. Full-source memory admission rejects oversized
work instead of silently switching to proxy statistics.

export.py prepares canonical statistics immediately at the pre-editor boundary.
FullDomain caches only five f64 sums plus a key, not image copies. The key hashes
all float32 source pixels, external-mask values, dimensions, colour boundaries,
smoothing, inversion and algorithm identity. Canonical row order is independent
of exporter tile size. Changed source/upstream edits/geometry/mask invalidate the
key. Offsets and uniformity strength do not change selection or the target.
The preview retains this small domain cache across renders; frozen exports own
independent caches. Original pixels and stats never become portable preset data.

## Selection, smoothing and scope

Continuous hue-wheel centre/width, saturation bounds and luminance bounds define
selection. Smoothing softens colour-domain boundaries, never spatially blurs.
Linked smoothing synchronizes both controls; unlink permits independent values.
All offsets and uniformity controls are finite -100..100, zero by default.
Positive uniformity converges to full-domain weighted targets; negative expands
variation. Hue uses circular, saturation-weighted direction and shortest arcs.
Input black offset and super-white scale are retained, with no intermediate SDR
RGB clipping. Bounded HSL component clipping is an explicit original algorithm
choice, not a proprietary parity claim.

Scope is explicit: all or current-local-mask. Local selection requires the current
valid objects/skin/brush grade mask. Object coverage follows the same portrait
warp; all masks follow manual geometry, optical coordinate sampling and crop.
Missing/unbound mask fails, never becomes global. Inversion complements colour
selection BEFORE multiplication by the external mask and geometry-valid coverage.
Batch replaces parameters and uses each target's own saved mask; source masks
cannot be transplanted through generic export. Source-bound mask reanalysis and
normal existing transfer restrictions remain in effect.

## Input picker and view-only range

The editor reuses the existing native color_picker_capture lease, file verification,
copy and presented acknowledgement, with the distinct colour_editor/master target
and colour-editor-input stage. The native sample request compares every proof
field to the eligible native lease and bounds the 1–121-pixel region. The engine
samples retained float input, not canvas/RGBA output. Source coverage rejects
padding. Cancellation at reader ingress interrupts full-source preparation.
The native UI displays the verified input in a modal; pointer sampling, arrow-key
coordinates, Enter and Esc are supported. Stale context unmounts it. Sampled
selection retains current draft offsets/uniformity rather than resetting them.

Show-range is temporary presentation state, absent from the recipe, project,
history, preset, batch and frozen export. Its renderer displays selected input
colour/rest grey, including outside local masks, bypassing downstream finishing.
Input/view renders still pass final source/asset checks before publication. The
regular export mode never reads the UI view toggle. Exact compositor-presented
preview receipts gate Apply; unknown commits query their original request ID.
One accepted Apply creates one non-coalesced reversible history transaction.

## Registered ports

- server.py: state/default/capture/restore/report, service ingress/dispatch,
  preview publication, source renderer, original-input capture and readback.
- vram.py: neutral stage ownership and explicit pre-editor source tap.
- export.py/export_recipe.py/export_snapshot.py: strict recipe snapshot, source
  stats, transformed mask, editor stage and source-sized delivery.
- full_quality.py/master16_policy.py: original-source inspection and no active
  editor RGB16 passthrough.
- scope.py + colour_editor_scope.py: independent lnx.colour_editor.v1 operation,
  existing preset/batch validation/history and target-specific render path.
- project.py: v22 editor schema; explicit v21 grain, v20 detail, v19 primary and
  older schemas preserved. Recursive editor injection in v21 or older rejects.
- ui/src-tauri: correlated native mailbox, frame presentation gate, verified
  picker proof admission and main/engine command/event registration.
- RetouchPanel.tsx, colourEditor components, native caps, preset and batch labels.
- packaging/build-colour-editor.sh and stage-engine.sh: offline packaged Rust ABI1,
  source/license inclusion; no runtime compilation or HSL numerical fallback.

## Primary references checked 2026-10-23

https://www.pixcakeai.com/guide/32455 (colour editor section, lines 329–360).
https://support.captureone.com/hc/en-us/articles/360002601358-The-Color-Editor-overview
https://support.captureone.com/hc/en-us/articles/360007944857-Making-local-adjustments-with-the-Color-Editor
https://www.captureone.com/blog/nail-down-exact-color-correction

Official control behavior is distinguished from original numerical choices:
normalised smoothing 0..1, hue offsets spanning ±180°, uniformity -100..100 and
weighted source target are our versioned policy. The guide does not specify
those numerical internals. This is not eight-band HSL, CMYK or an AI colour model.

## Outstanding acceptance

Qoder must run Rust/native/TS/package tests and inspect numerical, visual and
interaction behavior against all 15 controls. Full-resolution performance and
skin-tone/headroom quality are unverified. Existing native/host/CPU bridges are
not claimed as GPU-optimized. Required stress cases include stale/cancelled picker,
rapid slider latest-wins, source/mask changes, readback after unknown commit,
project old-schema injection, neutral bit identity, warped local masks, source
statistics equality across preview sizes/export tile sizes/inspection ROI,
view-toggle export exclusion, and batch atomicity with target-specific masks.
SHA256SUMS is source-integrity evidence only, never a passed-test certificate.
