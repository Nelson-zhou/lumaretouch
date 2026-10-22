# Professional-color targeted eyedroppers

Implementation scope, 2026-10-22. Authored/static-reviewed code is not runtime,
GPU, photographic, responsiveness or Qoder acceptance. No local application,
build, typecheck, test, model download or installation was run for this package.

## Exact handbook controls

The authoritative handbook professional-color section and AI requirement mapping
identify these controls, all linked to the official
[PC-32455 guide](https://www.pixcakeai.com/guide/32455):

| Control | Implemented consumer | Explicit boundary |
|---|---|---|
| PC-32455-C-8ebf8ee682 | Levels eyedropper group | RGB black/white actions only |
| PC-32455-C-58fb48cdf9 | Pick input black endpoints | No extra neutral/gamma picker |
| PC-32455-C-73ee12d5c4 | Pick input white endpoints | Existing output ranges retained |
| PC-32455-C-d30dc5a133 | Image-targeted point-curve adjustment on RGB, R/G/B, luminance | Retains existing PCHIP and linear-sRGB Y; not Lab L* |
| PC-32455-C-3791959b40 | Actual sampled HSL readout plus image-drag hue adjustment | Retains existing HSV-based 8-band renderer |

The guide specifies black/white input selection, multi-channel targeted curve
adjustments, and HSL sampling with horizontal hue dragging. It does not publish
an exact curve-node interpolation, hue-band solver or sample kernel. Those are
explicit Linux implementation choices, not claims to reproduce hidden internals.
White-balance's existing neutral eyedropper is unchanged. No exposure eyedropper
or unlisted levels-neutral picker is added. Color editor, grading, selective
color and other unlisted child controls are outside this package.

## Mature implementation comparison

Reviewed official/community source, not just marketing descriptions:

- [GIMP Levels tool](https://github.com/GNOME/gimp/blob/master/app/tools/gimplevelstool.c),
  `gimp_levels_tool_color_picked` and `levels_input_adjust_by_color`: distinguish
  input-black/input-white consumers and apply the RGB group to per-channel
  endpoints. LumaRetouch deliberately retains the existing master operation and
  samples its output before updating individual channel input endpoints, rather
  than silently resetting the user's master settings.
- [GIMP Curves tool](https://github.com/GNOME/gimp/blob/master/app/tools/gimpcurvestool.c),
  picked-color and point-addition paths: sample in a declared transfer domain,
  select the appropriate channel coordinate and reuse/add a curve point.
  Its value coordinate uses max RGB. LumaRetouch follows that master targeting
  convention while keeping its own existing PCHIP, parametric-before-master order
  and linear-sRGB luminance operation.
- [darktable color zones source](https://github.com/darktable-org/darktable/blob/master/src/iop/colorzones.c)
  and [official manual](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/color-zones/):
  the picker is tied to its module domain and targets smooth ranges. We preserve
  LumaRetouch's versioned eight-band HSV contract instead of silently substituting
  darktable's Lab/LCh algorithm. The new Rust bounded least-norm hue adjustment
  uses the exact existing unnormalized smoothstep basis; it changes only hue
  coefficients, preserving all saturation/value coefficients.

These are source paths inspected on 2026-10-22; moving master links are reference
material, not reproducible version claims. No third-party source was copied.

## End-to-end interaction and ownership

1. Launch the specific action/channel. App-scoped ownership disables conflicting
   coordinate tools and survives folding a panel. Starting a different unsubmitted
   tool cancels the old capture. An unresolved submitted receipt is not cancelled
   or silently resubmitted.
2. Render and publish a private LRCP frame from the actual input of the selected
   operation. Native epoch, document, recipe revision, capture generation/ticket,
   dimensions and projection accompany the pixels. The UI acknowledges only after
   that exact buffer is painted. RGBA8 is an aiming surface, never an inverse
   source for action math.
3. Pick a bounded 5×5 neighborhood, clipped at the image edge. Integer pixel
   coordinates refer to the frozen projected proxy. The producer re-evaluates that
   stage under the exact recipe proof and retains at most 121 RGB/coverage rows.
   Crop/rotation padding, nonfinite or outside-[0,1] target values fail closed.
4. Curve vertical drag and HSL horizontal drag propose scalar changes. One
   in-flight read-only request plus one latest pending intent prevents an unbounded
   pointer-move queue. A bounded 512-edge floating input thumbnail is retained
   solely for responsive same-operator stage feedback. The preview PNG is labelled
   tool-stage output, not final full-chain or full-resolution output. It does not
   update document recipes, history or exports.
5. The completed valid drag commits once after the matching latest proposal;
   a level click applies its endpoint selection once. A curve/HSL click without
   drag samples only. Escape/pointer cancellation before submission leaves the
   recipe unchanged. Numeric/keyboard interaction shares the same terminal path.
6. Preparation validates/redeems the producer's exact proof and Rust action plan
   before document mutation fencing. The controller installs only existing recipe
   fields and renders the real full chain. On render failure it restores the old
   recipe. Failed rollback is reported as outcome unknown/reload required.
7. Success is accepted only from the native-bound terminal post-history receipt,
   with matching identities, before/after recipe and undo/redo counts. Queue
   acceptance is never success. Timeout queries the original request; it does not
   execute it again. Request-ID replay is bounded and duplicate changed payloads
   reject.

## Numerical and persistence contracts

- Levels are display-sRGB: master first, then per-channel levels. Picking replaces
  only R/G/B input-black or input-white, preserving master, opposite endpoint,
  gamma and output range. Consequently a custom output range still maps to that
  range, not forcibly to physical black/white. Opposite endpoint crossing rejects
  rather than changing it behind the user's back. Disabled levels must first be
  explicitly enabled.
- Curves target the actual selected node input: after parametric for master,
  after master for R/G/B, after R/G/B for luminance. The selected node is inserted
  or reused under the existing spacing and 64-node rules. A zero effective drag
  does not insert a PCHIP node or upgrade a recipe version. V1 upgrades to V2 only
  for an effective luminance change. V3 parametric data remains intact. Disabled
  curves must first be enabled.
- HSL reports true HSL of the floating neighborhood mean. Rendering remains the
  existing HSV implementation with centers 0/30/60/120/180/240/280/320°, 45°
  smoothstep half-width and unchanged chroma gate. Neutral selections can still report HSL; nonzero hue changes on nearly neutral
  selections reject for unstable hue. A shared scale stops at the first hue-band limit;
  achieved delta is reported instead of claiming an unattainable shift.
- Scalar Rust uses binary64. Production stage/preview math uses existing
  NumPy/Torch float contracts. The 512-edge preview is an explicitly bounded
  proxy approximation, not a substituted export raster.
- Committed `_levels`, `_curves`, `_hsl` already belong to `DOC_FIELDS`, history
  snapshots, project/preset recipes, batch freezing, and `ExportSpec`. No capture,
  sampled rows, thumbnail or pending interaction is persisted into those recipes.
  Full exports use the unchanged existing full-resolution operators with the
  newly committed parameters. This structural integration is not yet a measured
  preview/export parity acceptance result.

## Authored checks and remaining acceptance

Authored narrow specifications: Rust `core/color_actions/picker_test.rs`, Python
`test_color_picker_actions.py`, `test_color_picker_stages.py` and
`test_color_picker_protocol.py`, plus the native/UI
contracts listed by their modules. They are not claimed passed. Existing CI may
compile/run them after publication; local test responsibility remains Qoder's.

Required runtime acceptance includes repeated and cancelled captures, crop plus
quarter/arbitrary rotations, nearly neutral and clipped/HDR targets, changed
channel/document/recipe during a probe, late arm response, receipt loss and engine
restart, panel collapse, each competing tool including SAM selection, invalid
endpoint/64-point boundaries, rapid-drag latest-wins behavior, real latency,
single undo/redo, save/reopen, preset/batch and full-resolution CPU/GPU exports.
