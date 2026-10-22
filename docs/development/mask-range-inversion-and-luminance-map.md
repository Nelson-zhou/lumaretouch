# Colour-range inversion and saved-mask luminance map

2026-10-22: implementation written and statically inspected only. No product run,
tests, build, typecheck, performance measurement, or visual acceptance was run.
The frozen source package remains research evidence, not an acceptance report.
PC-32454 as a whole is not complete.

## Frozen requirements and primary-source comparison

The handbook's local-colour section (manual-text lines 612–618) establishes colour
and luminance ranges and editable composed masks. The frozen AI package's
`功能需求验收映射.json` contains 78 PC-32454 children. The two addressed here are:

| Child | Stable control ID | Frozen path | Implemented semantics |
|---|---|---|---|
| 72 | PC-32454-C-f04c98eacf | 自定义蒙版/手动工具/颜色范围/显示蒙版反相 | Actual colour-range selection inversion, not negative-colour display |
| 75 | PC-32454-C-d078cd6b29 | 自定义蒙版/手动工具/亮度范围/显示明亮度图 | Source luminance diagnostic with **saved composed-mask** coverage, not an unapplied range-draft preview |

Each requirement ID is `LNX-REF-` followed by its control ID. Neither entry has
dedicated acceptance cases in the frozen package; COLOR-004 is only a related
module case and cannot stand in for child-level evidence.

Sources consulted on 2026-10-22:

- [PixCake local colour, colour/luminance range sections](https://www.pixcakeai.com/guide/32454)
  explicitly describes reversing the selected region for child 72, despite the
  display-oriented wording. It describes child 75 as displaying mask coverage.
  It does not publish a selection-distance formula, luminance transform, or the
  order of inversion and feathering.
- [Adobe Lightroom masking, Luminance Range and Invert a selection](https://helpx.adobe.com/lightroom/desktop/edit-photos/masking.html)
  distinguishes selection inversion from overlay modes. Its luminance map uses
  a monochrome representation with selected coverage still distinguished in
  colour. This implementation keeps the app's existing cyan rather than claiming
  Adobe colour/UI parity.
- [darktable community-maintained primary manual, parametric masks](https://docs.darktable.org/usermanual/development/en/darkroom/masking-and-blending/masks/parametric/)
  separates range-select/range-deselect polarity from channel/mask inspection.
  [Mask refinement and additional controls](https://docs.darktable.org/usermanual/development/en/darkroom/masking-and-blending/masks/refinement-controls/)
  documents a coloured mask over a monochrome image and separate refinement
  controls. We adopt those semantic distinctions, not its guided feathering or
  full processing-pipeline implementation.

## 72: a retained selection edit

Only `color_range` gains `invert:boolean`. Legacy v1 objects with the field absent
normalize to false. Non-booleans and that field on other kinds are rejected. New
objects default to false; re-sampling colour or adjusting tolerance preserves
the choice. It appears in both the ordinary range editor and capture review.

The existing controller validates and saves the object through the same reviewed
capture, history, project v4, source binding, and undo/redo path. The field is
data, not an executable expression or a second mask object. Canonical colour
objects include it; an older strict reader rejects an unsupported field rather
than silently converting an inverse selection into an ordinary one.

The Rust range body is unchanged when false. When true, it calculates
`1 - membership` only after immutable source RGB is present and finite. The
independently declared order is:

1. Original source colour membership (existing encoded-sRGB Euclidean metric).
2. Optional complement of this one colour-range operand.
3. Existing source-normalized, replicated-edge box feather.
4. Object opacity, then the existing ordered add/subtract/intersect fold.

This is not a claim about PixCake's undisclosed feather order. It preserves the
mature separation of selection polarity from strength and composition. The
current linear, constant-preserving box filter makes complement-before/after
feather equivalent in exact arithmetic; importantly, neither is equivalent to
complementing **after opacity**. Float rounding remains a local-test question.

No inverse is applied to projection padding or the display alpha. Missing or
nonfinite source samples, missing semantic operands, and unavailable prompted
operands retain existing fail-closed behavior. SAM2 binding validation and
transient lowering were not modified.

The private worker wire is LMR2. Colour records append a strict 0/1 u8 after the
four existing f64 values; other records are unchanged. Both endpoints reject
LMR1. A matching worker must be rebuilt by the later packaging/test owner. A
stale worker fails explicitly rather than accepting a misaligned or ignored flag.

## 75: display-only saved coverage and luminance

`display.ts` allocates new display buffers from the frozen capture. It never
writes into `VerifiedCapture.rgba`, whose alpha remains the engine's actual
saved-composition coverage. No CSS filter or newly thresholded range is treated
as a mask. The saved coverage is displayed as the existing cyan overlay at 55%
visual alpha, including fractional saved weights.

For valid source pixels, the base diagnostic computes sRGB-decoded linear-light
`Y = .2126 R + .7152 G + .0722 B`, then sRGB-encodes that Y into equal RGB display
channels. It uses the same Y calculation as the luminance eyedropper. RGB8
quantization, resampling, and crop/rotation interpolation mean this is explicitly
a **proxy diagnostic**, not a full-source, HDR, 16-bit, or export-quality proof.
The existing float-source Rust selection remains authoritative.

Producer-owned `sample_valid_rows` must be complete and valid for the map. Pixels
outside those spans appear as a neutral checkerboard with no coverage overlay;
they are not counted as black source pixels. Missing/invalid validity metadata,
no valid source pixels, or suspended saved coverage disables the map with a
reason. It does not disable manual range parameters. Ordinary saved-overlay and
sampling contracts remain separate.

While the map is on, saved cyan coverage is always shown; the ordinary overlay
preference is restored when it is off. Switching display mode does not restart
presentation acknowledgement, discard a geometry draft, alter source/model
identity, create a mutation/request, or write history. The eyedropper always
reads original frozen RGB8, never the grayscale canvas or cyan overlay. Closing
or starting a capture resets the display mode to normal RGB.

The map is available in saved-range viewing and range review. It intentionally
shows the **entire saved composition**, not just the selected object or current
unapplied draft. Both canvas and panel say this explicitly. Range or inversion
changes must be applied and a new saved-range capture opened before the displayed
coverage can reflect them. No live draft rasterizer or new adjustment consumers
are introduced in this slice.

## Focused acceptance handoff (not run)

These are proposed checks for the local test owner, not completed evidence:

1. **Legacy/schema/wire:** omitted and false inversion produce identical original
   colour coverage; true complements membership. Reject null/string/integer flags,
   flags on other kinds, invalid wire flag, LMR1, missing RGB, and nonfinite RGB.
   Repackage the matching worker rather than bypassing the version check.
2. **Operand order:** use matching/nonmatching patches with feather 0 and >0,
   opacity 0, 0.5, and 1; inspect add/subtract/intersect in different list positions.
   An enabled zero-opacity intersection still clears the composition. Missing
   semantic/prompted subtract operands still suspend the full consumer.
3. **Persistence/history/export:** apply one inverted object, undo/redo,
   save/reopen, and check full 8/16-bit exports. Source replacement or model mismatch
   must not rebind/silently broaden the mask. Confirm source geometry unchanged.
4. **Display math/alpha:** use black, neutral gray, white, red, green, and blue
   patches with saved alpha 0/128/255. Equal-colour pixels keep equal base gray
   regardless of alpha; cyan follows the stored alpha, not a threshold of Y.
   Snapshot original RGBA and descriptor before/after repeated mode switches.
5. **Validity/failure:** arbitrary rotation and empty row spans show neutral
   padding without selected coverage. Null/malformed/oversized rows or suspended
   mask disable the map without synthesizing a range. Ordinary manual controls
   remain available, and sampling in padding still does not change parameters.
6. **Interaction isolation:** sample the same source point before/after toggles;
   results match. Pending range edits do not change the displayed saved alpha.
   Toggle/close leaves history, proof identities, model identity, retained objects,
   and saved pixels unchanged. Applying inversion is one reviewed history edit;
   cancel makes none. Reopen saved view after Apply to see new coverage.
7. **Real product view:** verify keyboard focus, label legibility, scroll/zoom,
   drawing while switching diagnostic mode, source-capture cancellation, and
   memory/latency at supported proxy bounds. No performance claims are made here.
