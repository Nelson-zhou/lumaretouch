# Measured eye symmetry: source-only implementation

Status: AUTHORED / UNRUN. No product execution, imports, tests, collection,
compilation, typecheck, inference, downloads, numerical/photo/performance or
end-to-end acceptance was performed for this slice. This is a bounded original
implementation, not a claim of equivalence to PixCake's private algorithm.

## Exact requirements and reconciliation

Baseline: `223cb3657395914ca8be622436cee6ee1835c41f`.

- `LNX-REF-PC-32470-C-2745ac86f5`: 眼睛对称, family entry.
- `LNX-REF-PC-32470-C-a86e5c0175`: 眼睛对称/水平对称.
- `LNX-REF-PC-32470-C-4601eb7797`: 眼睛对称/大小对称.
- `LNX-REF-PC-32470-C-118aa67e04`: 眼睛对称/参考眼选择.

The supplied requirement mapping contains these at rows 3124, 3484, 3499 and
3514; each is research status with no dedicated acceptance case. PORTRAIT-009
is a related module case, not proof of any of these controls. The original
manual text at lines 533–537 preserves the eye-symmetry description.

Historical `portrait.md` audit package 44 was missing. Existing PC-32466 eye
shape controls are ten manually chosen bilateral displacements. Equal linked
slider amounts do not equalize measured eye size or level. They have no
reference-eye selection. This operation therefore is not another name for
manual eye size, eye spacing, iris size, position, gaze or face proportions.
Four requirement IDs remain one coherent user workflow, not four new algorithms
or an increase to the fixed handbook denominator. The old audit is not silently
rewritten as current whole-product acceptance.

## Primary semantics, technique and licenses

Read 2026-10-24:

- [Official iPad guide](https://www.pixcakeai.com/guide/32513), lines 78–84:
  independent eye leveling and size correction; size uses the larger eye by
  default and allows manually choosing a reference side.
- [Official iPad guide mirror](https://wiki.pixcakeai.com/guide/9810.html).
- [PixCake's desktop-oriented eye article](https://wiki.pixcakeai.com/portrait-retouching/15464.html):
  describes leveling as correcting high/low eye mismatch, not eye spacing.
- [Official MediaPipe v1.1.1 topology](https://raw.githubusercontent.com/google-ai-edge/mediapipe/v1.1.1/mediapipe/tasks/python/vision/face_landmarker.py):
  factual ordered 16-point eye contours and 5-point iris groups, already used
  by this repository. Subject left uses iris center 473; subject right uses
  468. These are not screen-side labels or complete clinical anatomy.
- [scikit-image primary TPS example](https://scikit-image.org/docs/stable/auto_examples/transform/plot_tps_deformation.html):
  destination-to-source estimation for inverse image warping.
- [OpenCV primary geometric transforms](https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html):
  inverse sampling rather than repeated forward image resampling.
- [scikit-image license](https://scikit-image.org/docs/stable/license.html):
  TPS implementation BSD-3-Clause. Technique was consulted only; no code,
  weights, assets, dependency or example image copied/downloaded.

The exact desktop baseline URL `/guide/32470` could not be opened by the
research tool. The accessible iPad sources and desktop-oriented article
corroborate the user semantics, not the desktop implementation. They do NOT
specify a head/image coordinate frame, size metric, fixed versus midpoint eye
level, numeric strength range, or exact gain. All choices below are explicitly
LumaRetouch policy. No 3D or AI-symmetry claim is made.

The existing `core/eye_shape/lib.rs`, `eye_shape_native.py`, inverse TPS,
protection and common sampler remain unchanged. They are the repository's
original GPL-3.0-or-later implementation; no incompatible upstream engine is
copied. Existing landmark/semantic producers and their model/license contracts
remain unchanged. The new Python/TypeScript source does not imply a new native
binary, new model or additional proven capability.

## Portable intent and actual source

Operation `lnx.eye_symmetry.v1` has exactly `version=1`, `horizontal` and `size`
in [0,1], and `reference` in `auto|left|right`. Defaults are 0, 0, auto. Only
these portable choices persist/inherit/transfer. No source points, areas,
resolved reference, output pixels, masks, paths or analysis travel as intent.
The reference selection applies to size only.

Both actual visible source eyes are required for any active correction. The
canonical owner retains exact effective original/derived source identity,
FaceRef and landmark digest; analysis is independently bound to that owner.
A decoded float buffer is not fraudulently hashed as the original encoded-file
SHA. Durable evidence dimensions describe the retained source/producer, not
every current preview/export grid. The existing `people_snapshot.at_dimensions`
retains normalized landmark bytes and source evidence while resampling semantic
coverage. This operation checks current RGB/mask shape and rebuilds geometry on
that actual grid; it does not reject a legitimate preview solely because its
size differs from the retained source. Full-resolution export uses true source
pixels, not an enlarged corrected proxy or displacement field. Existing
semantic resampling does not invent newly measured fine-edge information.
Source RGB and same-source exclusion evidence use the existing immutable
preparation contracts. Foreign/disabled retained
faces remain protected, not silently excluded from neighborhood safety.

The independent head axis uses observed forehead/chin evidence and nose-bridge
consistency, not the iris-to-iris vector. Using the latter to measure eye level
would define away the very difference being corrected. Source image pixels and
known occluders can veto a request but are not a complete eye/glasses/occlusion
segmentation model.

Level policy translates the two observed eye corner centers toward their mean
height along this independent head axis. Size policy compares actual 16-point
aperture polygon areas and isotropically scales the nonreference eye toward the
square-root area ratio. Auto resolves from each target's own eyes. A manually
chosen smaller reference can reduce the other eye. Isotropic area matching does
not separately force equal width, height, eyelid shape or iris appearance.

Actual forward offsets are generated by the existing Rust size (.12) and
position (.08 times eye width) slots using the new measured frame. Requests
outside the existing native bounds refuse; no clipped strength, enlarged
support, donor pixels or synthetic open eye substitutes are published. The
established destination-control inverse TPS and protected compact field feed
one canonical image/mask sampler. Its fold checks are sampled admission, not a
global mathematical proof of injectivity.

A nonzero strength on already matching measurements can legitimately yield a
measured identity. It must neither fabricate motion nor masquerade as missing
native code. Exact zero strengths bypass new anatomy/native work, even with a
retained left/right reference policy. The render planner exempts only the exact
valid reference enum from requiring analysis on its own; malformed leaves,
nonzero strengths, other operations and local assets retain their old rules.
Full recipe validation still runs. Canonical reset restores 0/0/auto together.

## Canonical integration

- `eye_symmetry_state.py`: strict portable state and actual shared ABI readiness.
- `eye_symmetry_native.py`: private native float64 snapshots, bounded conversion
  to the unchanged Rust controls; no Python replacement for generated offsets.
- `eye_symmetry_runtime.py`: independent measurements, real per-eye evidence,
  requested targets and guarded field construction.
- `eye_symmetry_people.py`: exact source/person ownership and composition after
  philtrum, preserving the original four slots and mouth slot 3.
- `people_algorithms.py`, `people_render_runtime.py`: canonical materialization,
  preparation, source-bound facts and the shared preview/export path.
- `creative_derived_effects.py`: exact new operation admission only; immutable
  derived-source and repaired-source proofs are not relaxed.
- `people_render_plan.py`: narrowly treats valid reference-only intent as not
  requiring rendered geometry; complete recipe validation is retained.
- `eye_symmetry_scope.py`, `people_scope.py`, `scope.py`, `workflow_ports.py`:
  explicit owner/source/FaceRef capture and target-only recomputation. Existing
  generic derived-preset guard remains; confirmed person transfer uses each
  target's own real analysis and complete candidate render before publication.
- `ui/src/eyeSymmetry`, RetouchPanel, people model, native capability and preset
  label: independent controls and reference selection, actual effective values
  with provenance, separate explicit shared intent, stale/pending/uncertain
  request fences, canonical history and reset. No extra edit/history owner.
- Registry extension and historical partial route inventory: traceable exact
  routes, not a full current product recount or acceptance result.

No previous operation is cleared, numerically converted or migrated. Existing
legacy compatibility rules, dormant history, source relocation, project
persistence, virtual copies and confirmed cross-owner association remain under
their established owners. Recipe transfer must not reuse the source's resolved
larger-eye side, measurements, pixels or semantic masks.

## Remaining limits and verification gates

- Bounded original head-relative leveling and aperture-area policy, not verified
  proprietary equivalence, clinical asymmetry treatment or full feature acceptance.
- Both eyes must be observable. Closed, occluded, clipped, strongly foreshortened,
  low-resolution/contrast or excessive corrections refuse. No eye, lid, gaze,
  missing iris or anatomy generation is implemented.
- Reference-eye size invariance is not a promise to keep that eye fixed when
  horizontal leveling is also requested. Horizontal leveling moves both eyes.
- Compact smoothing can affect surrounding tissue. Protected source anatomy and
  measured reference points are not complete per-pixel anatomical segmentation.
- Source measurement guarantees do not imply final symmetry after arbitrary
  overlapping prior eye/face geometry. Composition order is explicit; neither
  previous intent nor source texture is secretly replaced to force an outcome.
- Full float32 working-source, RGB8/RGB16 and immutable derived-source routes use
  existing range/opacity admission. Broad HDR/alpha are not enabled by clipping.
- Common sampler, finite-precision behavior and sampled fold checks remain;
  numerical naturalness, identity retention, acceptance on real photographs,
  performance, refusal prevalence and UI/history/export/preset execution are UNRUN.
- All other missing handbook features remain separate. No automatic segmentation,
  model compatibility or 32-tool creative completion is inferred from this slice.

## Freeze-time static evidence only

All 1,154 engine Python source files were parsed as AST without importing them.
Changed JSON was parsed, 119 previously recorded source byte hashes were checked
unchanged, and the diff whitespace check was clean. File ceilings remain
App 2,122 / main 2,042 / server 6,986 lines. These are static inspections, not
passed product tests.

Authored new fixtures contain 94 Python test functions (23 geometry, 27
integration, 20 state/native, 24 scope) and 20 UI test declarations, all UNRUN.
There is no new Rust solver or new Rust test claim. Integration positives use
native loader/control doubles but real new measurement/TPS and canonical
source paths. The 128 parameterized composition cases cover named synthetic
contour-wrapper prefix topologies, not all predecessor recipe semantics.
Scope transaction tests separately name their mocked renderer boundary. No
fixture count or source hash is substituted for numerical or photo acceptance.

Independent source review caught and resolved the durable-source versus current
render-grid mismatch and representability-loss versus true-identity distinction.
It found no further concrete blocker in the reviewed final sources, but cannot
establish that runtime tests, actual native binaries or photographs will pass.
